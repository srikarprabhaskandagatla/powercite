# PowerCite design

## 1. Goal

Rank business sites for behind the meter batteries, explain each rank, and trace every number to a source. Run offline on a cluster, push only small results, and show them on a static page.

**Not in scope.** Real meter data, feeder capacity, live search from the page, a trained ranking model (there are no labels yet).

## 2. Why these five towns

| Town | Utility | Why |
|---|---|---|
| Brockton | National Grid | Powertown's first market |
| Fall River | National Grid | a named next market |
| New Bedford | Eversource South Shore | a named next market, and a second utility with a different tariff |
| Worcester | National Grid | the largest of the five, Central Mass, a wider mix of industry |
| Lowell | National Grid | an old mill city in the north east of the state, a different building stock |

**Why only Massachusetts.** MassGIS publishes every town's parcels in one standard (L3). One loader works for all towns. Other states have no common format.

**Why not others yet.**
1. **Boston** is very large and on Eversource Greater Boston, a third tariff. It would dominate the results and the run time.
2. **Springfield** is on Eversource Western Mass, another tariff to add and check.
3. **Small and rural towns** have few commercial sites, which makes them a weak test of ranking.

Adding a town needs one line in `towns.json`. The code has no town specific logic except the utility map in `sources.json`.

## 3. Architecture

```
data_sources -> features -> embeddings -> scoring -> web
research ----------------> (tariffs.json) -^
rag (cited answers) ------------------------------^
```

| Stage | Input | Output |
|---|---|---|
| `data_sources` | Geofabrik pbf, MassGIS zips | per town buildings, grid, parcels (raw, not in git) |
| `features` | raw layers | `sites.csv`, one row per lot |
| `research` | 5 tariff and program pages | `tariffs.json` with quotes and URLs |
| `embeddings` | sites, named OSM buildings | `links.csv`, `lookalikes.csv`, `match_eval.json` |
| `rag` | cached pages, `questions.json` | `rag_answers.json` |
| `scoring` | sites, tariffs, links | `scored_sites.csv`, `ranked.csv` |
| `web` | all of the above | `docs/data/*.json` |

## 4. Key decisions

| Decision | Choice | Why | Rejected |
|---|---|---|---|
| OSM source | Geofabrik state pbf, read with pyosmium | Overpass blocked the cluster IP; one file covers all towns | Overpass, osmnx per town |
| Distance and area | EPSG:26986, meters | degrees give wrong areas and distances | EPSG:4326 math |
| Building to lot | `representative_point` within the lot | always inside the shape, one answer per building | centroid (can fall outside), intersects (14% hit 2 or more lots) |
| Condos | group tax records by `LOC_ID` | one lot can have hundreds of records | raw join, which duplicates sites |
| Floor area | assessor area if it is at least the footprint, else the footprint | assessor counts all floors but is sometimes missing | footprint only |
| Tariff extraction | rules by default, Claude structured output with a key | offline demo, same checks on both | LLM only |
| Fact checks | quote in page, value in quote, value in range | stops made up numbers | trust the model |
| Embedding model | bge small en v1.5, 384 dims, CPU | fast, strong on short text, has a search prefix | larger models, not needed at 7,912 records |
| Vector index | FAISS flat inner product | exact search, small data | HNSW, IVF (for state scale) |
| Name matching | embeddings plus address rules plus distance | embeddings alone reach 0.46 precision | embeddings only |
| Unclear matches | Claude judge only for the 0.55 to 0.70 band | cost and trust | LLM on every pair |
| Lookalikes | text vector plus number vector, weight 0.5 | text finds the kind, numbers find the size | either one alone |
| RAG chunks | 400 chars, 150 overlap, document header | the header lifts hit@3 from 57% to 93% | no header |
| Answers | Claude document blocks with citations, number check | every claim tied to cited text | free text answers |
| Score | weighted sum of 5 percentile features | no labels to train on; weights are shown and editable | LightGBM |
| Web | static page, Leaflet, precomputed JSON | free hosting, no keys, no server | Streamlit, a live API |

## 5. Evaluation

| What | How | Result |
|---|---|---|
| Name matching | the spatial join gives the true lot for each OSM building | precision 0.957, recall 0.554 |
| Lookalikes | share of neighbors with the same load type, size gap | 97%, 1.26x |
| RAG retrieval | 14 questions with expected page and text | hit@3 13 of 14 |
| Score sanity | rank correlation with peak kW | 0.91, the score mostly tracks size |

## 6. Commands

Set up the environment and the optional keys.

```bash
conda create -y -p ./envs/powercite python=3.12
conda activate ./envs/powercite
pip install -r requirements.txt
cp .env.example .env
```

Download the OpenStreetMap file (about 300 MB) into the raw data folder.

```bash
mkdir -p data/raw/osm
curl -L -o data/raw/osm/massachusetts-latest.osm.pbf https://download.geofabrik.de/north-america/us/massachusetts-latest.osm.pbf
```

Run every step from `src`, in this order. On the cluster each step ran as a small CPU SLURM job (1 core, 4 to 16 GB). Set `HF_HOME` to a scratch folder before the embedding steps.

```bash
cd src
python -m data_sources.extract_osm
python -m data_sources.fetch_grid
python -m data_sources.fetch_buildings
python -m data_sources.fetch_parcels
python -m features.join_parcels
python -m features.site_features
python -m research.fetch_pages
python -m research.extract_facts
python -m embeddings.embed_records
python -m embeddings.merge_records
python -m embeddings.lookalikes
python -m rag.answer
python -m scoring.score_sites
python -m scoring.explain
python -m web.export_data
```

The data, feature and matching steps take `--towns brockton lowell` to run a subset. `research.fetch_pages` and `research.extract_facts` take `--refresh` to skip the cache.

View the page.

```bash
python -m http.server 8765 --directory ../docs
```

## 7. Limits and next steps

| Limit | Next step |
|---|---|
| Peak kW from floor area | 12 months of interval data, then a dispatch model |
| Substation distance as a grid proxy | utility hosting capacity per feeder |
| One rate class rule for all utilities | per utility rules; Eversource G-1 runs to 100 kW |
| LLM paths not run live | run them, compare against the rules path |
| Match recall 0.55 | more candidates, OSM tags, tune the judge band |
| Five towns | all of Massachusetts as a SLURM array, approximate FAISS index |
