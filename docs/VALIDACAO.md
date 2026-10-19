# Validação do modelo com pontos de água reais (WPdx)

O app tem dois modelos, escolhidos no bloco **Model** da barra lateral:

- **v1 · approximations**: zonas hidrogeológicas por regra lat/lon, profundidade do lençol por uma
  regressão com coeficientes ilustrativos, vazão e permeabilidade fixas por zona, chuva interpolada
  de estações (GHCN + NASA POWER).
- **v2 · real data**: as mesmas fórmulas, com as entradas trocadas por dados reais:

| Entrada | Fonte na v2 |
|---|---|
| Vazão típica por poço e favorabilidade do aquífero | BGS Africa Groundwater Atlas (MacDonald et al. 2012), 5 km |
| Profundidade do lençol | GLOBGM v1.0 (Verkaik et al. 2024), steady-state, quartil inferior da célula |
| Chuva mensal | CHIRPS, climatologia 1991–2020 |
| Permeabilidade do solo | SoilGrids 2.0: `0,15 + 0,009·areia% − 0,006·argila%` (0,1–0,95) |

Onde uma célula não tem o dado real, a v2 usa o valor da v1. As zonas continuam como rótulo descritivo.

## Dados de verificação

**Water Point Data Exchange, WPdx-Basic** (`data.waterpointdata.org`, dataset `jfkt-jmqa`):
8.826 registros com país limpo = RDC.

- Usamos só os **7.956 com `country_id = CD`**. Os outros vêm de conjuntos de Uganda, Ruanda etc.
  com coordenadas dentro da RDC (provável erro de georreferência).
- **7.028 são poços** (`water_source_category = Well`); 79% funcionando (`status_id = Yes`).
- **90% vêm de um único levantamento** (GRET, 2014) e quase todos são **chafarizes** de redes
  alimentadas por poço: marcam o ponto de distribuição, não o poço.
- **Viés espacial forte**: a maioria está nos Kivus e em Kinshasa; **nenhum ponto na Cuvette
  Centrale**. Só 126 das 1.245 células (44 km) têm algum poço registrado.

Por isso tudo é medido **por célula** (uma célula "com poço registrado" tem ao menos um poço WPdx),
não por ponto, para que dezenas de chafarizes de uma mesma rede não pesem como dezenas de poços.

## Métricas (`POST /api/validation`)

| Métrica | O que mede |
|---|---|
| **AUC na área levantada** (principal) | Entre as células a até 50 km de algum ponto WPdx, chance de uma célula com poço registrado ter `P_poço` maior que uma sem registro. 0,5 = acaso |
| AUC estratificada por população | A mesma comparação no país todo, mas só entre células de população parecida (quintis do WorldPop 2020) |
| Recomendação de poço onde há poço registrado | % dessas células classificadas como poço (alto ou viável), comparado com a % em todas as células |
| `P_poço` médio com / sem registro | Nível de otimismo do modelo onde poços de fato existem |
| Poços funcionando por faixa de `P_poço` | Se poços em células com `P` alto falham menos |

## Resultados (parâmetros padrão)

**Grade de 44 km (1.245 células):**

| | v1 | v2 |
|---|---|---|
| AUC na área levantada (296 células) | 0,46 | 0,46 |
| AUC estratificada por população | 0,37 | 0,33 |
| Poço recomendado onde há poço registrado | 56% | **75%** |
| … em todas as células | 67% | 77% |
| `P_poço` médio, com / sem registro | 0,26 / 0,42 | **0,36** / 0,46 |
| Poços funcionando, `P` < 0,30 · 0,30–0,50 · ≥ 0,50 | 79% · 79% · 89% (n = 9) | 80% · 81% · 71% |

**Grade de 22 km (4.847 células):** AUC na área levantada 0,43 (v1) e 0,45 (v2); poço recomendado
onde há registro 48% → 63% (contra 64% → 73% em todas as células).

## O que isso quer dizer

1. **A v2 corrige o pessimismo da v1.** Nas células onde existem poços, a v1 recomendava poço menos
   do que no resto do país (56% contra 67%) e dava `P_poço` médio de 0,26. A v2 sobe para 75% e 0,36,
   em linha com o resto do país. A diferença vem principalmente do BGS: no Kasai, no rift e no
   embasamento a vazão típica real (~2,5 L/s) é bem maior que a estimada na v1 (0,5–1,2 L/s).
2. **Nenhuma das versões é validada como discriminante.** Dentro da área levantada, a AUC fica em
   0,43–0,47: o modelo não distingue onde há e onde não há poço registrado. A AUC estratificada por
   população fica abaixo de 0,5 porque as células "sem registro" incluem regiões nunca levantadas pelo
   WPdx (a Cuvette inteira), onde o modelo dá os maiores valores de `P`.
3. **O WPdx não consegue refutar o modelo.** Ele só registra poços que existem; perfurações secas
   não aparecem. E poços de abastecimento humano precisam de muito menos vazão que irrigação, então
   "existe um poço aqui" é um teste fraco para "aqui dá para irrigar com poço".
4. **Funcionamento não depende de `P_poço`** (~79–81% em todas as faixas): o que faz um poço parar é
   sobretudo manutenção e gestão, que o modelo não representa.

## Limitações conhecidas

- GLOBGM não é calibrado; a avaliação publicada é só contra observações dos EUA.
- As classes do BGS são qualitativas e foram estimadas a partir de vazões de poços: BGS e WPdx não são
  totalmente independentes.
- WorldPop (2020) e WPdx (2014, majoritariamente) são de anos diferentes.
- A fração de água superficial (JRC) é extraída (`water_frac`), mas ainda não entra no modelo.

## Próximos passos para uma validação de verdade

- Obter registros de perfuração com **sucesso e fracasso** (ex.: REGIDESO, ONGs de perfuração, ONHR)
  ou testes de bombeamento com vazão medida.
- Medir o nível de água em poços existentes para calibrar a profundidade do lençol (v2 usa GLOBGM).
- Incluir manutenção (custo anual e taxa de falha) no modelo, já que é o que mais explica poços parados.

## Como regenerar

```bash
python3 pipeline/build_data.py   # grade, DEM, clima, rios
python3 pipeline/build_bgs.py    # produtividade de aquíferos (BGS)
python3 pipeline/build_gee.py    # GLOBGM, CHIRPS, SoilGrids, WorldPop, JRC (Earth Engine, ~6 min)
python3 pipeline/build_wpdx.py   # pontos de água e área levantada
```

O Earth Engine só é usado nessa etapa; o app lê os arquivos gerados em `data/` e não precisa da
credencial. Para rodar o `build_gee.py`: `EE_PROJECT` e `EE_SERVICE_ACCOUNT_KEY` (JSON de conta de
serviço, fora do repositório) ou o login de `earthengine authenticate`.
