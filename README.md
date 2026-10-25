<h1 align="center">
  <br>
  PowerCite
  <br>
</h1>

<h4 align="center">Rank business sites for behind the meter batteries in five Massachusetts towns, with every number traced to its source.</h4>

<p align="center">
  <img src="https://img.shields.io/badge/-Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/-GeoPandas-139C5A?style=flat-square&logo=pandas&logoColor=white" alt="GeoPandas">
  <img src="https://img.shields.io/badge/-FAISS-0467DF?style=flat-square&logo=meta&logoColor=white" alt="FAISS">
  <img src="https://img.shields.io/badge/-Sentence%20Transformers-FFD21E?style=flat-square&logo=huggingface&logoColor=black" alt="Sentence Transformers">
  <img src="https://img.shields.io/badge/-Claude-D97757?style=flat-square&logo=anthropic&logoColor=white" alt="Claude">
  <img src="https://img.shields.io/badge/-Leaflet-199900?style=flat-square&logo=leaflet&logoColor=white" alt="Leaflet">
</p>

<p align="center">
  <a href="https://srikarprabhaskandagatla.github.io/powercite/">Live Demo</a>
  •
  <a href="#why-this-matters">Why It Matters</a>
  •
  <a href="#pipeline">Pipeline</a>
  •
  <a href="#results">Results</a>
  •
  <a href="#run">Run</a>
  •
  <a href="#files">Files</a>
  •
  <a href="#scope-and-honesty">Scope</a>
  •
  <a href="#license">License</a>
</p>

---

PowerCite joins tax parcels, OpenStreetMap buildings and the power grid into 6,311 business sites across Brockton, Fall River, New Bedford, Worcester and Lowell. It reads the utility tariff pages to find the real demand charge, then scores, ranks and explains every site. Embeddings match business names to parcels and find lookalike sites. A small RAG answers tariff questions with citations. The results are shown on a static map page in `docs/`, live at [srikarprabhaskandagatla.github.io/powercite](https://srikarprabhaskandagatla.github.io/powercite/).

The full design, with the reasons behind each choice, is in [docs/DESIGN.md](docs/DESIGN.md).

## Why this matters

A battery saves a business money by cutting its monthly peak, which is billed per kW. The hard part is finding which of thousands of buildings are worth a sales call. That needs land, grid, tariff and business data joined together. This project does that loop end to end.

```
Parcels + buildings + grid  ->  sites  ->  score and explain  ->  map
Tariff pages  ->  checked facts  +  cited answers
```

## Pipeline

1. **Data.** MassGIS parcels, OpenStreetMap buildings and grid from the Geofabrik file.
2. **Sites.** Each building is joined to its lot with a point inside the building, then grouped into one site per lot.
3. **Tariffs.** Demand charges come from the utility pages. Each value must appear word for word in the page.
   - *Rules mode (default)* uses regex. No network, safe for a demo.
   - *LLM mode (optional)* uses Claude with structured output. It runs only when a key is set, and the same checks apply.
4. **Embeddings.** bge small vectors in FAISS match OSM names to parcels and find lookalike sites.
5. **RAG.** Tariff pages are chunked with a document header, retrieved, and answered with citations.
6. **Score.** A weighted score of savings, load spikiness, open space, grid distance and data confidence, with a reason and a weak point for each site.
7. **Web.** A static page with a town dropdown, a map, live weight sliders and lookalikes.

## Results

| Measure | Value |
|---|---|
| Sites across five towns | 6,311 |
| Name match precision / recall | 0.957 / 0.554 |
| Embedding only precision | 0.463 |
| Lookalikes with the same load type | 97% |
| RAG hit at 3, with chunk headers | 13 of 14 |
| RAG hit at 3, without headers | 57% |

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
```

Keys in `.env` are optional. Without them, every step uses its cache or rules path.

The raw data download and the full run order are in the [design doc](docs/DESIGN.md#6-commands). To view the page with the data already in the repo

```bash
python -m http.server 8765 --directory docs
```

Then open port 8765 in a browser.

## Files

| Path | Purpose |
|---|---|
| `inputs/towns.json` | the five towns and their MassGIS ids |
| `inputs/sources.json` | tariff and program pages to fetch |
| `inputs/questions.json` | RAG evaluation questions |
| `src/config/` | paths and model assumptions |
| `src/data_sources/` | download parcels, buildings and grid |
| `src/features/` | join buildings to lots, build sites |
| `src/research/` | fetch pages, extract and check tariffs |
| `src/embeddings/` | record matching and lookalikes |
| `src/rag/` | chunk, retrieve and answer |
| `src/scoring/` | score, rank and explain |
| `src/web/` | export JSON for the page |
| `data/processed/` | small output tables |
| `docs/` | the map page and the design doc |

## Scope and honesty

This is a learning project built in a few days. Peak kW is estimated from floor area, not measured. Grid capacity is a distance to the nearest substation, not real feeder data. The demo ran without an API key, which means tariffs came from rules, pitch lines from templates, and RAG shows evidence without a written answer. The LLM paths are built and guarded but not yet run live. The rate class rule is the same for every utility, which overstates savings in New Bedford. A real tool would need interval meter data, hosting capacity maps and per utility rate rules.

## License

The code is under the [MIT License](LICENSE). The data keeps its own terms. OpenStreetMap data is under the Open Database License, with credit to OpenStreetMap contributors. MassGIS parcels are public data from the Commonwealth of Massachusetts. Tariff pages belong to their utilities and are cached only for reference.
