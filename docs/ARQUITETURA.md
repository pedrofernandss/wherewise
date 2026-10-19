# Plano de Arquitetura — Sistema de Inteligência Geoespacial para Acesso à Água na República Democrática do Congo

## 1. Visão geral

A República Democrática do Congo (RDC) ocupa a maior parte da Bacia do Congo, a segunda maior bacia hidrográfica do mundo, com extensos rios e aquíferos, mas a água não chega de forma distribuída às áreas agrícolas. A agricultura local depende fortemente da chuva (sequeiro), o que limita a produtividade e aumenta a vulnerabilidade à seca.

Este projeto propõe um **software de inteligência geoespacial** que recomenda, para cada região do país, a melhor estratégia de acesso à água:

- **Poço tubular** (água subterrânea), com estimativa de probabilidade de sucesso, profundidade esperada e custo; ou
- **Bombeamento de rio** (água superficial), com estimativa de vazão disponível, distância, elevação e custo operacional.

A recomendação leva em conta dados geográficos, climáticos, hidrológicos, de solo, de infraestrutura e econômicos, além do horizonte de planejamento (6 meses, 1 ano etc.).

### Clientes do produto

| Segmento | Uso principal |
|---|---|
| **Governo / ministérios** | Planejamento de políticas públicas, licitações e mapeamento de prioridades |
| **ONGs e agências de desenvolvimento** | Priorização de investimentos, elaboração de projetos e relatórios de impacto |
| **Empresas privadas de irrigação e perfuração** | Prospecção de locais viáveis, cálculo de orçamento e redução de risco |

### Escopo inicial

- Dois tipos de recomendação: **poço tubular** e **bombeamento de rio**.
- Região de foco: **República Democrática do Congo** (RDC, Congo-Kinshasa), 26 províncias.
- Horizontes: 6 meses, 1 ano e customizável.
- Visualização em mapa por regiões, com percentual de probabilidade para poços.

---

## 2. Datasets e fontes de dados

### 2.1 Hidrogeologia e águas subterrâneas

| Fonte | Dado | Resolução / Escala | Licença | URL |
|---|---|---|---|---|
| **Africa Groundwater Atlas (BGS/UPGro)** | Perfis hidrogeológicos por país, mapas e shapefiles | Nacional / subnacional | Aberto | https://www.bgs.ac.uk/africagroundwateratlas/ |
| **WHYMAP (BGR/UNESCO)** | Mapas hidrogeológicos mundiais, aquíferos transfronteiriços | Várias escalas | Aberto / não comercial | https://www.whymap.org/ |
| **IGRAC — GGIS** | Metadados, poços e polígonos de aquíferos | Variável | Aberto (registro em alguns casos) | https://www.un-igrac.org/global-groundwater-information-system-ggis |
| **GRACE / GRACE-FO** | Anomalias de armazenamento subterrâneo (proxy indireto) | ~300 km | Aberto | https://grace.jpl.nasa.gov/ |

> A Cuvette Centrale (centro-oeste da RDC) possui aquíferos sedimentares rasos e as maiores turfeiras tropicais do mundo, ambientalmente sensíveis. Os planaltos Kalahari/Batéké (Kinshasa, Kwango, Kwilu) têm areias espessas com lençol profundo; o Kongo Central e o Katanga têm calcários e dolomitos com possível carste; o embasamento cristalino (Kasai, norte e leste) e o rift do Kivu apresentam aquíferos fraturados de vazão baixa e variável.

### 2.2 Hidrografia superficial (rios, bacias, vazão)

| Fonte | Dado | Resolução / Escala | Licença | URL |
|---|---|---|---|---|
| **HydroSHEDS** | Rede de drenagem, direção de fluxo, bacias, acumulação | 3 a 30 arc-seconds (~90 m a 1 km) | Aberto | https://www.hydrosheds.org/ |
| **GRDC** | Séries temporais de vazão in situ | Diária / mensal (por estação) | Aberto para pesquisa (cadastro) | https://grdc.bafg.de/ |
| **OpenStreetMap / Geofabrik** | Rios, lagos, represas (vetorial) | Vetorial, atualizado diariamente | ODbL | https://download.geofabrik.de/africa/congo-democratic-republic.html |
| **WRI Aqueduct 4.0** | Indicadores de risco hídrico, escassez, estresse | ~5 arc-minutos (~10 km) | CC BY 4.0 | https://github.com/wri/Aqueduct40 |

### 2.3 Clima, precipitação e umidade

| Fonte | Dado | Resolução / Escala | Licença | URL |
|---|---|---|---|---|
| **CHIRPS** | Precipitação diária, pentadal, mensal | 0,05° (~5,5 km) | CC0 | https://www.chc.ucsb.edu/data/chirps |
| **CHIRTS** | Temperatura máxima diária | 0,05° | Domínio público | https://www.chc.ucsb.edu/data/chirts |
| **ERA5 / ERA5-Land** | Precipitação, temperatura, umidade, evapotranspiração, vento | 0,25° / 0,1° (~9 a 31 km) | Aberto (CDS) | https://cds.climate.copernicus.eu/ |
| **TerraClimate** | Balanço hídrico mensal, ET, runoff, déficit, PDSI | ~4 km | Aberto | https://www.climatologylab.org/terraclimate.html |
| **WorldClim 2.1** | Normais climáticas e variáveis bioclimáticas | 30 s a 10 min (~1 km a 20 km) | Aberto | https://www.worldclim.org/ |

### 2.4 Solo, uso da terra e agricultura

| Fonte | Dado | Resolução / Escala | Licença | URL |
|---|---|---|---|---|
| **SoilGrids 2.0 (ISRIC)** | Textura, profundidade, drenagem, capacidade de água disponível | 250 m, 6 profundidades | CC BY 4.0 | https://soilgrids.org/ |
| **ESA WorldCover** | Cobertura do solo (11 classes) | 10 m | CC BY 4.0 | https://esa-worldcover.org/ |
| **FAO WaPOR** | Evapotranspiração real, produtividade da água, umidade do solo | 100 m / 300 m (África) | Aberto | https://www.fao.org/in-action/remote-sensing-for-water-productivity/ |

### 2.5 Infraestrutura, população e topografia

| Fonte | Dado | Resolução / Escala | Licença | URL |
|---|---|---|---|---|
| **WorldPop** | Densidade populacional | 100 m | CC BY 4.0 | https://www.worldpop.org/ |
| **GHSL (JRC/Copernicus)** | Assentamentos, população, construções | 38 m a 1 km | Uso livre com atribuição | https://ghsl.jrc.ec.europa.eu/ |
| **OpenStreetMap / Geofabrik** | Estradas, cidades, mercados, infraestrutura | Vetorial | ODbL | https://download.geofabrik.de/africa/congo-democratic-republic.html |
| **SRTM / NASADEM** | Modelo digital de elevação (DEM) | 1 arc-second (~30 m) | Aberto | https://lpdaac.usgs.gov/products/nasadem_hgtv001/ |

### 2.6 Dados complementares

| Fonte | Dado | Licença | URL |
|---|---|---|---|
| **World Bank Open Data** | Recursos hídricos internos renováveis, indicadores socioeconômicos | CC BY 4.0 | https://data.worldbank.org/indicator/ER.H2O.INTR.K3?locations=CG |
| **Artigos técnicos** | Hidrogeologia da Cuvette Centrale e de ambientes fraturados (inclui estudos da vizinha República do Congo como análogos) | Variável | Ver referências na seção 7 |

---

## 3. Cálculos e modelos

### 3.1 Notação comum

| Símbolo | Significado | Unidade |
|---|---|---|
| `P` | Precipitação média anual | mm/ano |
| `ET` | Evapotranspiração real | mm/ano |
| `R` | Recarga de aquífero | mm/ano |
| `WTD` | Profundidade do lençol freático | m |
| `GPI` | Groundwater Potential Index (índice de potencial de água subterrânea) | 0 a 1 |
| `Q_rio` | Vazão média do rio mais próximo | m³/s |
| `D` | Distância até o rio mais próximo | m |
| `Δz` | Diferença de elevação entre captação e destino | m |
| `C_poço` | Custo total de um poço | USD |
| `C_bombeamento` | Custo operacional de bombeamento de rio | USD/ano |
| `IR` | Índice de recomendação | 0 a 1 |

### 3.2 Estimativa de profundidade do lençol freático (WTD)

Quando não há poços de monitoramento suficientes, a WTD pode ser inferida por regressão ou machine learning a partir de covariáveis espaciais:

```
WTD = β₀ + β₁·E + β₂·S + β₃·C + β₄·D_d + β₅·P + β₆·ET + β₇·So + β₈·NDVI + ε
```

| Variável | Descrição |
|---|---|
| `E` | Elevação do terreno (m) |
| `S` | Declividade (%) |
| `C` | Curvatura do terreno |
| `D_d` | Distância até a drenagem mais próxima (m) |
| `P` | Precipitação média anual (mm/ano) |
| `ET` | Evapotranspiração real (mm/ano) |
| `So` | Tipo/permeabilidade do solo (categórico ou normalizado) |
| `NDVI` | Índice de vegetação |
| `βᵢ` | Coeficientes calibrados com dados de poços conhecidos |

> **Princípio**: vales, depressões e áreas de recarga tendem a WTD menor; topos e áreas distantes de drenagens tendem a WTD maior.

### 3.3 Estimativa de recarga do aquífero

#### Balanço hídrico simplificado

```
R = P - ET - R_sup - ΔS
```

Onde `R_sup` é o escoamento superficial e `ΔS` a variação de armazenamento no solo.

#### Método do coeficiente de recarga

```
R = α · P
```

Onde `α` é o coeficiente de recarga. Para a região tropical úmida da RDC, valores típicos podem variar entre **0,15 e 0,35**, dependendo do solo, litologia e cobertura vegetal.

#### Índice de aridez

```
AI = P / PET
```

- `AI < 0,5`: árido/semiárido, baixa recarga
- `AI > 0,65`: subúmido/úmido, maior recarga

### 3.4 Índice de potencial de água subterrânea (GPI)

O GPI combina fatores hidrogeológicos e ambientais por soma ponderada:

```
GPI = Σ wᵢ · xᵢ
```

Fatores típicos normalizados entre 0 e 1:

| Fator | Fonte | Direção do peso |
|---|---|---|
| Distância a drenagens | HydroSHEDS / OSM | Menor distância = maior potencial |
| Densidade de drenagem | HydroSHEDS | Maior densidade = maior potencial |
| Declividade | SRTM | Menor declive = maior potencial |
| Precipitação / recarga | CHIRPS / TerraClimate | Maior recarga = maior potencial |
| Tipo de solo / permeabilidade | SoilGrids | Maior permeabilidade = maior potencial |
| Uso da terra | ESA WorldCover | Vegetação densa/áreas de recarga = maior potencial |
| Litologia / hidrogeologia | Africa Groundwater Atlas / WHYMAP | Aquíferos favoráveis = maior potencial |

Os pesos `wᵢ` podem ser definidos por **AHP** (Analytic Hierarchy Process) ou calibrados com dados de poços produtivos/improdutivos.

#### Consistência AHP

```
CR = CI / RI
CI = (λ_max - n) / (n - 1)
```

Se `CR < 0,1`, a matriz de comparações é considerada consistente.

### 3.5 Probabilidade de sucesso de um poço

A probabilidade final de encontrar água em um poço em determinado local pode ser expressa como:

```
P_poço = GPI · (1 - WTD / WTD_max) · (R / R_ref)
```

Onde:

- `WTD_max`: profundidade máxima economicamente viável (ex: 60 m para bombas solares de baixo custo).
- `R_ref`: valor de referência de recarga para a região (ex: 200 mm/ano).

O resultado `P_poço` varia de **0 a 1** e é exibido ao usuário como **percentual**.

### 3.6 Custo estimado do poço

```
C_poço = C_fixo + (c_perf · H) + (c_revest · H) + C_bomba + C_inst
```

| Variável | Descrição | Valor de referência |
|---|---|---|
| `C_fixo` | Mobilização, estudos, testes de bombeamento | USD 500–2.000 |
| `c_perf` | Custo de perfuração por metro | USD 40–120/m |
| `c_revest` | Custo de revestimento/casing por metro | USD 20–50/m |
| `H` | Profundidade total do poço (m) | `H = WTD + h_saturado` |
| `C_bomba` | Bomba submersível / solar | USD 500–3.000 |
| `C_inst` | Instalação, painéis solares, caixa d'água, tubulação | USD 300–2.000 |

> A profundidade `H` considera `h_saturado` (altura mínima de aquífero saturado a ser interceptada, tipicamente 5–10 m).

### 3.7 Viabilidade do bombeamento de rio

#### Adequação do bombeamento de rio

```
A_sup = min(1, Q_rio / Q_demanda) · (1 - Δz / Δz_max) · (1 - D / D_max)
```

| Variável | Descrição |
|---|---|
| `Q_rio` | Vazão média do rio mais próximo (m³/s) |
| `Q_demanda` | Vazão demandada pelo projeto (m³/s) |
| `Δz` | Diferença de elevação entre captação e destino (m) |
| `Δz_max` | elevação máxima economicamente aceitável (m) |
| `D` | Distância até o rio (m) |
| `D_max` | Distância máxima aceitável (m) |

#### Custo operacional de bombeamento

```
C_bombeamento = (ρ · g · Q · H_t / η) · t · c_energia
```

| Variável | Descrição | Valor típico |
|---|---|---|
| `ρ` | Densidade da água | 1.000 kg/m³ |
| `g` | Gravidade | 9,81 m/s² |
| `Q` | Vazão bombeada | m³/s |
| `H_t` | Altura manométrica total | m |
| `η` | Eficiência da bomba | 0,4 a 0,7 |
| `t` | Tempo de operação anual | h/ano |
| `c_energia` | Custo da energia | USD/kWh |

A altura manométrica total inclui:

```
H_t = Δz + h_f + h_s + h_d
```

Onde `h_f` é a perda de carga na tubulação (Darcy-Weisbach ou Hazen-Williams), `h_s` a altura de sucção e `h_d` a altura de recalque.

### 3.8 Índice de recomendação: poço vs bombeamento de rio

O sistema decide entre as duas alternativas por meio de um índice integrado:

```
IR = w₁ · A_sub + w₂ · A_sup + w₃ · E_custo + w₄ · R_clima + w₅ · A_acesso
```

| Componente | Cálculo |
|---|---|
| `A_sub` (adequação do poço) | `GPI · (1 - WTD / WTD_max) · (R / R_ref)` |
| `A_sup` (adequação do rio) | `min(1, Q_rio / Q_demanda) · (1 - Δz / Δz_max) · (1 - D / D_max)` |
| `E_custo` (eficiência de custo) | `C_bombeamento / (C_poço + C_bombeamento)` — ou custo anualizado total invertido |
| `R_clima` (confiabilidade climática) | Para rios: meses com `Q_rio ≥ Q_min` / período total; para poços: `R_seco / R_med` |
| `A_acesso` (acessibilidade) | Combina distância a estradas, centros urbanos e densidade populacional |

Os pesos `wᵢ` são ajustáveis pelo usuário ou definidos por AHP.

#### Regra de decisão

```
Se IR > 0,5 → Recomendar poço tubular
Se IR ≤ 0,5 → Recomendar bombeamento de rio
```

> A recomendação é preliminar. Estudos hidrogeológicos de campo (sondagem, teste de bombeamento) são sempre necessários antes da obra.

### 3.9 Refinamento com machine learning

Com dados de campo (coordenadas de poços, profundidade real, vazão, sucesso/fracasso), o modelo pode ser refinado com:

- **Random Forest** ou **XGBoost** para classificação (poço produtivo / improdutivo) ou regressão (vazão estimada).
- **AHP supervisionado**: pesos ajustados com base na importância das variáveis do modelo treinado.

---

## 4. Arquitetura na Azure

### 4.1 Visão geral

```
Usuário (governo, ONG, empresa)
        │
        ▼
┌─────────────────────────────────────────────┐
│  Frontend web / dashboard                   │
│  • React + Azure Maps Web SDK               │
│  • Mapas de recomendação por região         │
│  • Percentual de probabilidade (poços)      │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  API / Backend (Azure Container Apps)       │
│  • Python + FastAPI                         │
│  • Cálculo de scores e recomendações        │
│  • Orquestração de RAG                      │
│  • ETL geoespacial (rasterio, xarray, GEE)  │
└─────────────────────────────────────────────┘
        │
        ├──► Azure Maps REST API (geocoding, rotas, tiles)
        │
        ├──► Azure AI Search + Azure OpenAI (RAG)
        │
        ├──► Azure Database for PostgreSQL Flexible Server + PostGIS
        │
        └──► Azure Data Lake Storage Gen2 (rasters, shapefiles, GeoJSON)
```

### 4.2 Componentes

| Camada | Serviço Azure | Função |
|---|---|---|
| **Mapas e visualização** | Azure Maps (Gen2) + Web SDK | Mapa base, camadas de calor/regiões, geocoding, rotas e isócronas |
| **Backend / API** | Azure Container Apps | Hospedar a API Python (FastAPI), processamento e orquestração |
| **Banco geoespacial** | Azure Database for PostgreSQL Flexible Server + PostGIS | Armazenar geometrias, scores, poços, rios e metadados |
| **Armazenamento de dados brutos** | Azure Data Lake Storage Gen2 | Rasters TIFF/COG, NetCDF, shapefiles, GeoJSON, relatórios |
| **RAG / LLM** | Azure AI Search + Azure OpenAI (gpt-4o-mini + embeddings) | Consulta a documentos técnicos, legislação e relatórios |
| **ML (opcional no MVP)** | Azure Machine Learning | Treinamento e deploy de modelos de ML geoespacial |
| **Monitoramento** | Azure Application Insights + Log Analytics | Logs, métricas e alertas |

### 4.3 Avaliação do uso de RAG

**RAG (Retrieval-Augmented Generation) faz sentido neste projeto? Sim, com escopo bem definido.**

#### Onde aplicar

| Caso de uso | Benefício do RAG |
|---|---|
| **Consulta a documentos técnicos** | Responder perguntas sobre hidrogeologia da RDC, critérios de perfuração, legislação ambiental |
| **Geração de relatórios** | Criar resumos de viabilidade em linguagem natural a partir dos dados calculados |
| **Suporte ao tomador de decisão** | Explicar por que uma região foi recomendada como "poço" ou "rio" |
| **Atualização contínua** | Ingerir novos artigos, relatórios de campo e normas sem re-treinar modelo |

#### Como funciona na arquitetura

1. **Ingestão**: documentos (PDFs, artigos, legislação, relatórios técnicos) são carregados no Azure Data Lake.
2. **Chunking e embedding**: o texto é dividido em trechos e convertido em vetores com **Azure OpenAI text-embedding-3-small**.
3. **Indexação**: vetores e metadados são armazenados no **Azure AI Search**.
4. **Consulta**: o usuário faz uma pergunta; o sistema busca os trechos mais relevantes e os envia para o **gpt-4o-mini** gerar uma resposta fundamentada.

#### Exemplo de fluxo RAG

```
Usuário: "Quais as restrições ambientais para perfuração de poços na província de Équateur?"
        │
        ▼
Azure AI Search recupera trechos de legislação + artigos técnicos
        │
        ▼
Azure OpenAI gera resposta: "Em Équateur, na Cuvette Centrale, as turfeiras são áreas sensíveis. Recomenda-se ..."
```

#### Limitações e cuidados

- O RAG **não substitui** modelos hidrológicos; serve apenas para interpretar e contextualizar informações textuais.
- É necessário validar as respostas contra fontes primárias.
- Para o MVP, o RAG pode ser desativado ou limitado a um conjunto pequeno de documentos.

---

## 5. Visualização

### 5.1 Mapa de recomendação por regiões

- A área da RDC é dividida em células (ex: 1 km × 1 km ou por divisão administrativa).
- Cada célula recebe uma cor indicando a recomendação:
  - **Verde escuro**: poço altamente recomendado
  - **Verde claro**: poço viável
  - **Azul**: bombeamento de rio recomendado
  - **Amarelo**: análise inconclusiva / necessita campo
  - **Vermelho**: não recomendado

### 5.2 Mapa de probabilidade para poços

- Quando a recomendação for **poço**, exibir o percentual de probabilidade de encontrar água (`P_poço × 100`).
- Camada de calor (heatmap) mostrando a confiança do modelo.
- Tooltip com:
  - Probabilidade estimada (%)
  - Profundidade estimada (m)
  - Custo estimado (USD)
  - Principal fator positivo / negativo

### 5.3 Comparativo por período

- O usuário seleciona o horizonte (6 meses, 1 ano, customizado).
- O sistema recalcula `R_clima` e custos, atualizando a recomendação.

---

## 6. Custo estimado do MVP na Azure

### Cenário mínimo viável (validação, poucos usuários)

| Componente | Configuração | Custo mensal (USD) |
|---|---|---|
| Azure Maps | Dentro do free tier ou poucas requisições | $0–20 |
| Data Lake Gen2 | 100 GB Hot | $2–5 |
| Azure Container Apps | Dentro do free tier ou carga leve | $0–10 |
| PostgreSQL Flexible + PostGIS | B1MS + 32 GB | ~$20 |
| Azure AI Search | Free tier | $0 |
| Azure OpenAI | Uso mínimo de embeddings + gpt-4o-mini | $5–15 |
| **Total** | | **~$30–70/mês** |

### Cenário pequeno produtivo

| Componente | Configuração | Custo mensal (USD) |
|---|---|---|
| Azure Maps | ~50K transações | $50–200 |
| Data Lake Gen2 | 500 GB Hot + 1 TB Cold | $15–30 |
| Azure Container Apps | 1 réplica + processamento | $20–40 |
| PostgreSQL Flexible + PostGIS | B2S + 64 GB | $60–75 |
| Azure AI Search | Basic tier | ~$74 |
| Azure OpenAI | Uso moderado | $20–50 |
| Azure ML / Databricks | Opcional/esporádico | $0–50 |
| Monitoramento | Application Insights | $5–15 |
| **Total** | | **~$260–550/mês** |

> Assinaturas novas no Azure recebem **USD 200 de crédito por 30 dias**, o que cobre os primeiros meses de MVP.

---

## 7. Roadmap sugerido

### Fase 1 — Fundação (semanas 1 a 3)

- [ ] Definir AOI (Área de Interesse) piloto na RDC (sugestão: províncias de Kinshasa e Kongo Central).
- [ ] Baixar e catalogar datasets prioritários: SRTM, HydroSHEDS, CHIRPS, SoilGrids, OSM.
- [ ] Montar ambiente Azure: PostgreSQL + PostGIS, Data Lake, Container Apps.
- [ ] Criar pipeline de ETL inicial para raster e vetores.

### Fase 2 — Modelo e API (semanas 4 a 7)

- [ ] Implementar cálculo de WTD, recarga e GPI.
- [ ] Calcular `P_poço`, `A_sup`, `IR` e regra de decisão.
- [ ] Desenvolver API FastAPI com endpoints de recomendação por coordenada, região e período.
- [ ] Criar base de dados de poços/rios no PostGIS.

### Fase 3 — Visualização e RAG (semanas 8 a 10)

- [ ] Implementar frontend com Azure Maps Web SDK.
- [ ] Exibir camadas de recomendação e probabilidade de poços.
- [ ] Configurar Azure AI Search + OpenAI para RAG com documentos técnicos.

### Fase 4 — Validação e ajuste (semanas 11 a 14)

- [ ] Comparar recomendações com dados de campo (se disponíveis).
- [ ] Calibrar pesos do modelo com AHP/ML.
- [ ] Coletar feedback de governos, ONGs e empresas.

### Fase 5 — Escala (após o hackaton)

- [ ] Expandir para as demais províncias da RDC.
- [ ] Integrar dados de sensores e cadastro colaborativo de poços.
- [ ] Evoluir modelo com machine learning supervisionado.

---

## 8. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Dados escassos ou de baixa qualidade em certas regiões | Usar proxies (SRTM, NDVI, precipitação) e indicar nível de confiança |
| Previsões imprecisas de poços | Sempre recomendar sondagem antes da perfuração; exibir probabilidade, não certeza |
| Variabilidade sazonal extrema | Usar séries temporais longas (CHIRPS, TerraClimate) e múltiplos horizontes |
| Acesso e conectividade limitada no campo | Criar relatórios PDF offline e cache de regiões prioritárias |
| Complexidade de deploy geoespacial | Container Apps + Docker simplificam dependências (GDAL, rasterio) |
| Custo do Azure crescer | Começar por free tiers e escalar conforme uso real |

---

## 9. Referências técnicas selecionadas

1. **Mouakoumbat, N. J. L. et al.** Hydrogeological characterization and approach to a conceptual model of the aquifer of the Cuvette Basin, Republic of Congo. *International Journal of Geosciences*, 2022. (República do Congo; análogo para a Cuvette Centrale da RDC.)
2. **Dinga, J. B. et al.** Contribution of Remote Sensing to Groundwater Prospecting in Fractured Environments: The Case of Pointe-Noire. *Journal of Water Resource and Protection*, 2026. (República do Congo; análogo para aquíferos fraturados.)
3. **Tshimanga, R. M. et al.** A Catchment Information System to Advance Systems-Based Management of Large Tropical River Basins. *Research Square*, 2026.
4. **Tshimanga, R. M. et al.** Congo basin peatlands as coupled human–natural systems. *Royal Society Publishing*, 2026.
5. **MacDonald, A. M. et al.** Quantitative maps of groundwater resources in Africa. *Environmental Research Letters*, 2012.
6. **British Geological Survey.** Africa Groundwater Atlas, incluindo a página de hidrogeologia da República Democrática do Congo. https://www.bgs.ac.uk/africagroundwateratlas/
7. **HydroSHEDS.** https://www.hydrosheds.org/
8. **CHIRPS.** https://www.chc.ucsb.edu/data/chirps
9. **SoilGrids.** https://soilgrids.org/
10. **Microsoft Azure.** Documentação de Azure Maps, Container Apps, PostgreSQL Flexible Server, Azure AI Search e Azure OpenAI.

---

## 10. Resumo executivo para o pitch

**Problema**: A República Democrática do Congo tem água, mas não infraestrutura para levá-la à agricultura. A maioria dos plantios depende da chuva.

**Solução**: Software geoespacial que recomenda, região a região, se o melhor caminho é **perfurar um poço** ou **bombar água de um rio**, com cálculos de probabilidade, profundidade, vazão e custo.

**Diferencial**: Integra dados abertos globais (BGS, HydroSHEDS, CHIRPS, SoilGrids, OSM) com modelos hidrológicos e machine learning, exibindo tudo em mapas interativos na Azure.

**Clientes**: Governo, ONGs e empresas privadas de irrigação.

**Tecnologia**: Azure Maps, Container Apps, PostgreSQL + PostGIS, Data Lake, Azure AI Search + OpenAI (RAG).

**Custo MVP**: A partir de **USD 30–70/mês** no cenário mínimo.
