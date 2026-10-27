<h1 align="center">
  <br>
  PowerCite
  <br>
</h1>

<h4 align="center">A 15 step offline pipeline that finds which businesses in five Massachusetts towns would gain the most from a battery, with every number traced to its source.</h4>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/-Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://geopandas.org/">
    <img src="https://img.shields.io/badge/-GeoPandas-139C5A?style=flat-square&logo=pandas&logoColor=white" alt="GeoPandas">
  </a>
  <a href="https://github.com/facebookresearch/faiss">
    <img src="https://img.shields.io/badge/-FAISS-0467DF?style=flat-square&logo=meta&logoColor=white" alt="FAISS">
  </a>
  <a href="https://www.sbert.net/">
    <img src="https://img.shields.io/badge/-Sentence%20Transformers-FFD21E?style=flat-square&logo=huggingface&logoColor=black" alt="Sentence Transformers">
  </a>
  <a href="https://www.anthropic.com/">
    <img src="https://img.shields.io/badge/-Claude-D97757?style=flat-square&logo=anthropic&logoColor=white" alt="Claude">
  </a>
  <a href="https://leafletjs.com/">
    <img src="https://img.shields.io/badge/-Leaflet-199900?style=flat-square&logo=leaflet&logoColor=white" alt="Leaflet">
  </a>
  <a href="https://developer.mozilla.org/en-US/docs/Web/JavaScript">
    <img src="https://img.shields.io/badge/-JavaScript-grey?style=flat-square&logo=javascript&logoColor=F7DF1E" alt="JavaScript">
  </a>
</p>

<p align="center">
  <a href="#what-it-does">What It Does</a>
  •
  <a href="#setup">Setup</a>
  •
  <a href="#architecture">Architecture</a>
  •
  <a href="#pipeline-stages">Pipeline Stages</a>
  •
  <a href="#website">Website</a>
  •
  <a href="#evaluation">Evaluation</a>
  •
  <a href="#design-choices-and-trade-offs">Design Choices</a>
  •
  <a href="#known-limitations">Known Limitations</a>
  •
  <a href="#license">License</a>
</p>

<p align="center">
  <strong>Live Demo</strong> <a href="https://srikarprabhaskandagatla.github.io/powercite/">srikarprabhaskandagatla.github.io/powercite</a>
</p>

---

## What It Does

A battery saves a business money by cutting its monthly peak, which the utility bills per kW. The hard part is knowing which of thousands of buildings are worth a sales call. That needs land, building, grid and tariff data joined together.

PowerCite joins MassGIS tax parcels, OpenStreetMap buildings and the power grid into **6,311 business sites** in Brockton, Fall River, New Bedford, Worcester and Lowell. It reads the utility's own rate sheets to find the real demand charge. Then it scores, ranks and explains every site. Embeddings match business names to parcels and find lookalike sites in any town. A small RAG answers rate questions with the source text.

The result is a map page. Each site has a **fit** from 0 to 100, a guess of the **money a month** a battery could bring, a plain reason, and five similar sites.

The full list of design decisions is in [docs/DESIGN.md](docs/DESIGN.md).

---

## Setup

**Requirements.** Python 3.12 and about 1 GB of disk for raw data. API keys are optional. Without them every step uses its cache or rules path.

```bash
git clone https://github.com/srikarprabhaskandagatla/powercite.git
cd powercite
conda create -y -p ./envs/powercite python=3.12
conda activate ./envs/powercite
pip install -r requirements.txt
cp .env.example .env
```

**View the page with the data already in the repo.**

```bash
python -m http.server 8765 --directory docs
```

Then open port 8765 in a browser.

**Rebuild everything from raw data.** Download the OpenStreetMap file (about 300 MB), then run each step from `src` in the order of the [pipeline stages](#pipeline-stages). The exact commands are in the [design doc](docs/DESIGN.md#6-commands).

```bash
mkdir -p data/raw/osm
curl -L -o data/raw/osm/massachusetts-latest.osm.pbf https://download.geofabrik.de/north-america/us/massachusetts-latest.osm.pbf
```

On the cluster each step ran as a small CPU job with 1 core and 4 to 16 GB.

---

## Architecture

There are two lanes. The left lane builds and ranks sites. The right lane reads the rate pages. They meet at scoring and at the website.

```
 MassGIS parcels   OSM buildings   OSM grid              Utility rate and program pages
        |                |             |                              |
        +----------------+-------------+                              |
                         |                                            |
                         v                                            v
              1 to 6   BUILD SITES                          7 to 8   READ PAGES
              one site per lot, 6,311 sites                 $/kW with a checked quote
                         |                                     |              |
                         v                                     |              |
              9 to 10  MATCH NAMES                             |              |
              embeddings plus address rules                    |              |
                         |                                     |              |
                         v                                     |              |
              11       FIND LOOKALIKES                         |              |
              text plus number vectors                         |              |
                         |                                     |              |
                         v                                     |              |
              13 to 14 SCORE AND EXPLAIN  <--------------------+              |
              5 features, fit, reason                                         |
                         |                                   12   RAG        |
                         v                                   chunks, top 3 <--+
              15       EXPORT  <-------------------------------------+
              small JSON files for the page
                         |
                         v
                      WEBSITE
```

| Step | Module | Output |
|---|---|---|
| 1 | `data_sources/extract_osm.py` | state substations, power lines and buildings |
| 2 | `data_sources/fetch_grid.py` | town boundary, substations and lines per town |
| 3 | `data_sources/fetch_buildings.py` | business buildings per town |
| 4 | `data_sources/fetch_parcels.py` | parcels with tax records per town |
| 5 | `features/join_parcels.py` | each building tied to its lot |
| 6 | `features/site_features.py` | `sites.csv`, one row per lot |
| 7 | `research/fetch_pages.py` | cached rate and program pages |
| 8 | `research/extract_facts.py` | `tariffs.json` |
| 9 | `embeddings/embed_records.py` | site and OSM vectors |
| 10 | `embeddings/merge_records.py` | `links.csv`, `match_eval.json` |
| 11 | `embeddings/lookalikes.py` | `lookalikes.csv` |
| 12 | `rag/answer.py` | `rag_answers.json` |
| 13 | `scoring/score_sites.py` | `scored_sites.csv` |
| 14 | `scoring/explain.py` | `ranked.csv` per town |
| 15 | `web/export_data.py` | `docs/data/*.json` |

**Three rules hold everywhere.**
1. **Offline first.** Every network or model call sits behind a cache or a key check. With no key, rules and templates take over.
2. **Heavy work on the cluster, small results in git.** Raw data never goes in the repo.
3. **Every number is traceable.** Rates carry a quote and a URL. Answers carry the source text.

### File Structure

```
powercite/
├── inputs/
│   ├── towns.json          # the five towns and their MassGIS ids
│   ├── sources.json        # rate and program pages, and the utility of each town
│   └── questions.json      # 14 RAG test questions with the expected page
├── src/
│   ├── config/             # paths, units and model assumptions
│   ├── data_sources/       # steps 1 to 4, raw layers
│   ├── features/           # steps 5 and 6, sites
│   ├── research/           # steps 7 and 8, pages and checked tariff facts
│   ├── embeddings/         # steps 9 to 11, matching and lookalikes
│   ├── rag/                # step 12, chunks, retrieval and answers
│   ├── scoring/            # steps 13 and 14, score and explain
│   └── web/                # step 15, export for the page
├── data/
│   ├── cache/              # cached pages and extractions
│   └── processed/          # small output tables
└── docs/
    ├── index.html          # the map page
    ├── data/               # JSON the page reads
    └── DESIGN.md           # design decisions and commands
```

---

## Pipeline Stages

### Step 1. Extract OSM (`data_sources/extract_osm.py`)

**What it does.** Reads the Massachusetts OpenStreetMap file once and keeps the substations, power lines and buildings around the five towns.

**How it works.**
- Reads the Geofabrik `.pbf` file with pyosmium, inside a box around all five towns with a small pad.
- Keeps power lines tagged `line` or `minor_line`, and substations with their name, operator, type and voltage.
- Keeps every building with its name, address and business tags.

**Problem solved.** The cluster IP was blocked by the public Overpass servers. One local file covers every town and never fails mid run.

---

### Step 2. Grid per town (`data_sources/fetch_grid.py`)

**What it does.** Cuts the grid layers down to each town.

**How it works.**
- Gets the town boundary once from OpenStreetMap and caches it.
- Keeps substations and lines within 5 km of the town, which catches a substation just over the border.
- Works in meters (EPSG 26986, Massachusetts State Plane).

---

### Step 3. Business buildings (`data_sources/fetch_buildings.py`)

**What it does.** Keeps only buildings that could be a business.

**How it works.** A building stays if its type is commercial, retail, industrial, office, warehouse, school, hotel and similar, or if it has a `shop`, `amenity`, `office` or `craft` tag.

---

### Step 4. Parcels (`data_sources/fetch_parcels.py`)

**What it does.** Downloads the MassGIS L3 parcels for each town and joins the tax records to the lot shapes.

**How it works.**
- Downloads the town zip from MassGIS and keeps the `FEE` and `TAX` lot shapes.
- Joins tax records to shapes on `LOC_ID`.
- Groups condo records first. One lot can have hundreds of tax records, and each would become a fake site. The group keeps the first use code, address and owner, and sums the values and areas.
- Maps the first digit of the state use code to a class, like commercial or industrial.

**Problem solved.** OSM knows the building and often the business name. MassGIS knows the lot, owner, use and floor area. Neither one is enough alone.

---

### Step 5. Building to lot (`features/join_parcels.py`)

**What it does.** Ties each building to the one lot it stands on.

**How it works.** Takes one point that is always inside the building (`representative_point`) and tests it `within` the lots.

**Problem solved.** Testing the whole shape put 14% of Brockton buildings on 2 or more lots, because outlines touch neighbors. A centroid can fall outside an L shaped building. The inside point gives one clean answer.

---

### Step 6. Site features (`features/site_features.py`)

**What it does.** Turns buildings and lots into one site per lot, with size, load type, peak and grid distance.

**How it works.**
- Keeps lots in the commercial, industrial, exempt and mixed classes with at least 250 m2 of footprint.
- **Floor area.** Uses the assessor area if it is at least the footprint, otherwise the footprint. The assessor counts every floor but is sometimes missing.
- **Load type.** Keywords in the use description, like grocery, restaurant, office or warehouse.
- **Peak kW** is floor area times watts per m2 for that load type, for example 160 for a grocery and 20 for a warehouse.
- **Open lot** is lot area minus the building footprints.
- **Grid.** Distance from the site to the nearest distribution substation, in meters.

**Output.** `sites.csv` per town. 6,311 sites in all, from 916 in Lowell to 2,102 in Worcester.

**Trade off.** Peak kW from floor area is a rule of thumb. It is the weakest number in the project, and it drives most of the ranking.

---

### Step 7. Fetch pages (`research/fetch_pages.py`)

**What it does.** Downloads the five pages that set the money. That is three rate sheets (National Grid, Eversource South Shore, Eversource Greater Boston) and two ConnectedSolutions program pages.

**How it works.** Each page is cleaned to text and saved with its URL, fetch time and sha256. Later runs read the cache. `--refresh` fetches again.

---

### Step 8. Extract tariff facts (`research/extract_facts.py`)

**What it does.** Finds the demand charge per kW for the G-2 and G-3 rate classes of each utility.

**How it works.**
- **Rules mode (default).** Regex finds lines like "Demand $10.48 per kW".
- **LLM mode (optional).** Claude with structured output, used only when a key is set.
- Both modes face the same three checks. The quote must be in the page, the number must be in the quote, and the number must be in a sensible range. A value that fails is dropped.

**Output.** `tariffs.json`, with the rate, the quote and the URL for each town and class.

**Problem solved.** A made up rate would make every dollar on the page wrong. The checks make that impossible to miss.

---

### Step 9. Embed records (`embeddings/embed_records.py`)

**What it does.** Turns short text about each site and each named OSM building into a vector.

**How it works.**
- A site record is `owner; address, town; use`. An OSM record is `name; address, town; kind`.
- The model is `bge-small-en-v1.5`, with 384 dimensions, run on CPU.
- Vectors are normalized, which makes inner product equal to cosine.

---

### Step 10. Match names (`embeddings/merge_records.py`)

**What it does.** Links each named OSM business (like "Shaw's") to its parcel (owner "SHAWS REALTY TRUST").

**How it works.**
1. For each OSM building, takes the top 20 sites by embedding from a FAISS `IndexFlatIP`, plus the 5 nearest lots by distance.
2. Scores each pair as half cosine and half address score. House numbers must overlap.
3. Accepts a pair at 0.70 or above within 200 m.
4. Pairs from 0.55 to 0.70 go to a Claude Haiku judge, only when a key is set.

**Output.** `links.csv` with 1,601 OSM rows, 723 of them linked.

**Problem solved.** The two sources share no ID. Embeddings alone got 46% precision. They know Shaw's is a grocery, but not which Shaw's. Address rules and distance took it to 96%.

**Trade off.** Recall is 0.55. A wrong name on a sales lead is worse than no name, which is why precision came first.

---

### Step 11. Find lookalikes (`embeddings/lookalikes.py`)

**What it does.** For every site, finds the 5 most similar sites in any of the five towns.

**How it works.**
- A **text vector** from the use, load type and linked names.
- A **number vector** from log floor area, peak kW, open lot, substation distance and building count, each scaled to the same range.
- Both are joined with weights of 0.5 each. The inner product is then a weighted sum of the two cosines.

**Problem solved.** Text alone finds the same kind of business at any size. Numbers alone find the same size of any kind. The mix finds both.

---

### Step 12. RAG (`rag/build_index.py`, `rag/answer.py`)

**What it does.** Answers rate questions with the exact source text.

**How it works.**
1. Splits each page into 400 character chunks with 150 of overlap.
2. Puts a header on each chunk, like "Eversource South Shore rates, page 3".
3. Embeds the chunks with the same bge model into FAISS.
4. For each question, adds the bge search prefix and takes the top 3 chunks.
5. With a key, Claude answers from those chunks with citations, and every number in the answer must appear in them. Without a key, the page shows the chunks.

**Problem solved.** Rate sheets repeat the same line names for every class. "Customer Charge $370" means nothing without knowing it is Eversource G-2. The header took hit at 3 from 57% to 93%.

---

### Step 13. Score (`scoring/score_sites.py`)

**What it does.** Works out the money and the fit for every site.

**Money a month.**

| Part | How |
|---|---|
| Rate class | under 20 kW peak is G-1 with no demand charge, 200 kW or more is G-3, the rest is G-2 |
| Battery size | 25% of the peak, at most 100 kW |
| Lower bill | battery kW times the demand rate from step 8 |
| Program pay | battery kW times $200 a year over 12 months, counted only if "$200/kW" is on the cached program page |
| Money a month | lower bill plus program pay, before the battery's cost |

**Fit, from 0 to 100.** Five features, each from 0 to 1, times a weight.

| Feature | How | Weight |
|---|---|---|
| Savings | percentile of the lower bill among all sites | 0.45 |
| Spikes | a fixed number per load type, restaurants highest | 0.15 |
| Space | open lot over 500 m2, at most 1 | 0.15 |
| Grid | 1 minus the percentile of substation distance | 0.15 |
| Data | assessor area 0.5, linked name 0.25, known substation voltage 0.25 | 0.10 |

**Worked example.** Montello Heel Manufacturing in Brockton has an estimated peak of 481 kW and is on G-3 at $10.48 per kW. The battery is 100 kW. The lower bill is $1,048 and the program pay is $1,667, which gives $2,715 a month. Its fit is 89.6 and it ranks first in Brockton.

**Trade off.** A weighted sum, not a trained model. There are no labels yet of which sites bought a battery. The weights are shown on the page and can be changed.

---

### Step 14. Explain (`scoring/explain.py`)

**What it does.** Writes a reason and a weak point for each site.

**How it works.**
- Compares each of the five parts with the median site.
- **Reason.** The two parts where the site beats the median most, written with real numbers.
- **Weak point.** The part furthest below the median, only if one is below it.
- **Pitch line.** With a key, Claude Sonnet writes one line for the top 20 in each town, and every number in it must be in the site facts. Without a key, a template builds it from the reason.
- Keeps the top 300 sites per town in `ranked.csv`.

---

### Step 15. Export (`web/export_data.py`)

**What it does.** Writes the small JSON files the page reads.

**How it works.**
- `towns.json` lists the towns.
- One file per town holds its top 300 sites, the town boundary simplified to 20 m, its substations, the 5 lookalikes of each site, and its rates with quotes.
- `rag.json` holds the questions and their source chunks.

---

## Website

The page is one HTML file in `docs/`, with plain JavaScript and Leaflet. It has no server, no keys and no build step. It reads only the JSON from step 15.

### Layout

| Part | What it shows |
|---|---|
| Header | the PowerCite name, the town in the middle, and the Town, Priorities and theme buttons |
| Rankings | the top 300 sites with rank, fit and money a month, scrolling on its own |
| Map | one dot per site and a square per substation, filling the rest of the screen |
| Site card | opens on the map when a site is picked, with the fit, money, reason, breakdown and details |
| Similar results | the 5 lookalikes of the picked site, from any town |
| Rates | 3 demo questions with a short answer and the quote from the source |

### What happens on each action

1. **Pick a town.** The page loads that town's file, fits the map to its border, and draws the dots and the list.
2. **Pick a site** from the list or the map. The card opens, the other dots fade, and the lookalikes load. Clicking a lookalike in another town opens that town on the same site.
3. **Move a Priorities slider.** The page scores every site again with the new weights. The list, the colors and the card update right away, and each row shows how far it moved.
4. **Pick a rate question.** The short answer and the quote appear, and the map shows which sites it is about. A G-3 question colors the G-3 sites. A program question colors the sites that get program pay. A question about another utility offers a button to go to that town.
5. **Ask box.** A placeholder for live questions. It replies that the feature is under construction.

### Reading the map

- **Color is fit.** Stronger orange means a better fit, split into five equal groups.
- **Size is money.** A bigger dot means more money a month.
- Light and dark themes are both built in, and the page remembers the choice.

---

## Evaluation

| What | How | Result |
|---|---|---|
| Name matching | the spatial join gives the true lot for each OSM building, a free answer key | precision 0.957, recall 0.554 |
| Embedding only matching | same answer key | precision 0.463 |
| Lookalikes | share of the 5 with the same load type, and the size gap | 97%, 1.26x |
| RAG retrieval | 14 questions, each with the page and text that must be found | hit at 3, 13 of 14 with headers, 57% without |
| Score sanity | rank correlation of fit with peak kW | 0.91 |

### Matching, method by method

| Method | Precision | Recall |
|---|---|---|
| Embedding only | 0.463 | 0.227 |
| Fuzzy address only | 0.659 | 0.506 |
| Text combined | 0.931 | 0.543 |
| **Text plus location (final)** | **0.957** | **0.554** |

---

## Design Choices and Trade-offs

### Problem. Two data sources with no shared ID
**Solution.** Embeddings find the candidates, address rules and distance decide. The spatial join doubles as a free answer key to measure it.

### Problem. LLMs can make up numbers
**Solution.** The LLM proposes and code verifies. A tariff value needs its quote in the page. An answer or pitch needs each number in its source. Anything that fails is dropped or replaced by the rules path.

### Problem. Rate sheets look the same for every class
**Solution.** A document header on every chunk. It was the biggest single win in retrieval.

### Problem. There are no labels to train a ranker
**Solution.** Five percentile features with weights anyone can read and change on the page.

### Problem. Free hosting and no running costs
**Solution.** Everything heavy runs offline. The page is static and reads precomputed JSON.

### Trade-off. Exact FAISS search
Exact search is fine at 7,912 records. The whole state would need an approximate index.

### Trade-off. Top 300 per town on the page
It keeps each town file small and the map readable. Lower ranked sites stay in `scored_sites.csv`.

---

## Known Limitations

- **Peak kW is a rule of thumb** from floor area, not meter data. It drives most of the ranking, which is why the fit tracks size (0.91).
- **One rate class rule for every utility.** Eversource South Shore G-1 runs up to 100 kW with no demand charge, which means New Bedford savings are too high.
- **Substation distance stands in for grid capacity.** Real feeder hosting capacity would be better.
- **The LLM paths have not run live.** The demo had no API key. Tariffs came from rules, pitch lines from templates, and the RAG shows source text only.
- **Match recall is 0.55.** About half of the named OSM businesses are not linked.
- **Money a month is before the battery's cost.** It is not a payback.
- **Five towns only.** The same code runs on any Massachusetts town with one line in `inputs/towns.json`.

---

## License

The code is under the [MIT License](LICENSE). The data keeps its own terms. OpenStreetMap data is under the Open Database License, with credit to OpenStreetMap contributors. MassGIS parcels are public data from the Commonwealth of Massachusetts. Tariff pages belong to their utilities and are cached only for reference.
