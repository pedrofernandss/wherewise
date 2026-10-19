# Parâmetros do projeto de irrigação

O bloco **Irrigation project** da barra lateral descreve um projeto de irrigação hipotético. Para cada
célula do mapa, o app pergunta: *para abastecer este projeto aqui, é melhor perfurar poço(s) ou bombear
água de um rio?* Mudar um controle recalcula o mapa inteiro.

O cálculo está em `backend/app/model.py` (função `evaluate`) e, idêntico, em `frontend/model.js`
(demo estática). O teste `test_parity.py` garante que os dois dão o mesmo resultado.

## Os quatro controles

| Controle | Faixa | Padrão | Parâmetro |
|---|---|---|---|
| Irrigated area | 1–100 ha | 5 ha | `area_ha` |
| Energy cost | 0,05–0,60 USD/kWh | 0,22 | `c_energia` |
| Max. viable depth | 20–150 m | 60 m | `WTD_max` |
| Max. distance to river | 2–40 km | 15 km | `D_max_km` |

### Irrigated area: quanta água é preciso

A área define a vazão que a bomba precisa entregar enquanto está ligada:

```
q_dem = area_ha × irrigation_mm_day × 10 / (hours_per_day × 3600)      [m³/s]
```

Com os padrões (5 ha, 5 mm/dia, 8 h/dia): 250 m³/dia, ou **~8,7 L/s** durante o bombeamento.

Essa vazão alimenta:

- **Número de poços**: `ceil(q_dem / vazão típica por poço da zona)`, limitado a 20. Se nem 20 poços
  cobrem a demanda, a adequação do poço é penalizada (×0,6) e a explicação avisa.
- **Rio**: só se pode captar 10% da vazão do rio no período (vazão ecológica, `env_flow_frac`). Se isso
  não cobre `q_dem`, a adequação do rio cai na mesma proporção.
- **Custos**: diâmetro do tubo, potência da bomba e energia crescem com `q_dem`.

Efeito típico: áreas grandes desfavorecem o poço onde o aquífero rende pouco (embasamento cristalino,
0,5–0,7 L/s por poço) e desfavorecem o rio onde ele é pequeno.

### Energy cost: preço da energia de bombeamento

O padrão (0,22 USD/kWh) equivale a diesel ou solar fora da rede elétrica. Ele multiplica o custo de
operação das duas opções:

```
potência (kW) = ρ · g · q_dem · H_total / η / 1000
custo de energia = potência × horas de bombeamento no horizonte × c_energia
```

`H_total` é a altura que a água precisa subir: no poço, profundidade do lençol + rebaixamento + pressão
de saída; no rio, desnível rio→lavoura + perda de carga no tubo (Hazen-Williams) + alturas de sucção e
recalque. Quanto mais cara a energia, mais pesa essa altura no índice de custo (`E_custo`).

### Max. viable depth (WTD_max): até que profundidade de lençol vale perfurar

A probabilidade de sucesso do poço é multiplicada por `(1 − WTD / WTD_max)`:

```
P_poço = GPI × (1 − WTD / WTD_max) × min(1, R / R_ref)
```

Com `WTD_max = 60 m`, um lençol a 30 m corta a probabilidade pela metade; a partir de 60 m o poço sai
como inviável. Esse limite também decide se o fator explicativo aparece como *shallow* ou *deep water
table* (abaixo ou acima de `WTD_max / 2`).

### Max. distance to river (D_max): até onde vale puxar água de um rio

A adequação do rio cai linearmente com a distância e chega a zero em `D_max`:

```
A_sup = min(1, vazão captável / q_dem) × (1 − desnível / Dz_max) × (1 − distância / D_max)
```

Rios além de `D_max` ficam com adequação zero. Aumentar o valor abre mais células para a opção
*River pumping*; a adutora mais longa também encarece o capex (`D_m × (8 + 150 × diâmetro)`).

## Horizonte e mês de início

As horas de bombeamento no horizonte não são fixas: cada mês pesa pela **necessidade de irrigação**,
`1 − chuva / evapotranspiração potencial` (entre 0,15 e 1). Começar em junho, início da estação seca no
sul da RDC, concentra meses secos e encarece a operação; a vazão do rio no período também segue a
sazonalidade da chuva (amortecida pelo regime de cada rio).

## Parâmetros fixos (não aparecem na tela)

Todos ficam em `Params` (`backend/app/model.py`) e em `DEFAULTS` (`frontend/model.js`); a API aceita
qualquer um deles em `params` (por exemplo, `POST /api/recommendations` com
`{"params": {"irrigation_mm_day": 6}}`).

| Parâmetro | Padrão | Significado |
|---|---|---|
| `irrigation_mm_day` | 5,0 mm/dia | lâmina de irrigação de pico |
| `hours_per_day` | 8 h | horas de bombeamento por dia |
| `eta` | 0,55 | eficiência do conjunto motor-bomba |
| `R_ref` | 200 mm/ano | recarga de referência (acima disso não aumenta `P_poço`) |
| `h_sat` | 8 m | perfuração abaixo do lençol (`H = WTD + h_sat`) |
| `drawdown` | 5 m | rebaixamento do nível no poço bombeado |
| `C_fixo` | USD 1.200 | custo fixo por poço |
| `c_perf` / `c_revest` | USD 70 / 35 por m | perfuração / revestimento |
| `C_bomba` / `C_inst` | USD 1.500 / 1.200 | bomba e instalação por poço |
| `c_mob_km` | USD 15 por km | mobilização da sonda por km até a estrada |
| `max_wells` | 20 | máximo de poços por projeto |
| `Dz_max` | 100 m | desnível rio→lavoura em que a adequação do rio zera |
| `env_flow_frac` | 0,10 | fração máxima captável da vazão do rio |
| `C_bomba_rio` / `C_captacao` | USD 2.500 / 1.500 | bomba e captação no rio |
| `hazen_C` | 140 | coeficiente de Hazen-Williams do tubo |
| `pipe_v` | 1,0 m/s | velocidade de projeto (define o diâmetro) |
| `h_s` / `h_d` | 3 m / 10 m | alturas de sucção e de pressão de saída |

Os custos são ordens de grandeza para comparação entre as opções, não orçamento de obra.

## Como os resultados viram a recomendação

Os componentes acima entram no índice de recomendação `IR` (pesos ajustáveis em **IR index weights**):

```
IR = w1·A_sub + w2·(1 − A_sup) + w3·E_custo + w4·R_clima + w5·A_acesso     (normalizado pela soma dos pesos)
```

`IR > 0,5` favorece o poço. As classes do mapa (altamente recomendado, viável, rio, inconclusivo, não
recomendado) estão descritas em "Decisões de modelagem" no [README](README.md).
