Role & Contexto
Você é um Engenheiro de Software Full-Stack e Arquiteto Cloud. Nosso MVP de inteligência geoespacial já está com a interface pronta (React + Azure Maps) e a lógica de cálculo definida no backend (Python/FastAPI).

Sua Tarefa
Preciso que você crie o módulo do chatbot acoplável ao sistema. Será um "Floating Chat Widget" no canto inferior direito integrado a um backend FastAPI. Para o RAG, utilizaremos a Bing Web Search API da Azure (Web RAG / Tool Calling) para que o chatbot pesquise na internet em tempo real sobre clima, hidrogeologia e legislação, mantendo toda a arquitetura dentro do ecossistema Microsoft.

Stack do Chatbot:

Frontend: stack atual do projeto

Backend: Rota em FastAPI (/api/chat).

LLM & Orquestração: Claude API 

Ferramenta de Busca (Web RAG): BingSearchRun e BingSearchAPIWrapper.

Entregáveis Solicitados:

Ícone de bolha de chat flutuante.

Janela de chat (estilo Intercom) com input, botão de enviar e indicador de carregamento.

Conexão via fetch para o endpoint /api/chat.

Estilização (ChatWidget.css):

Design corporativo moderno e responsivo.

Backend FastAPI (rotas_chat.py):

Endpoint POST /api/chat recebendo o histórico e o prompt.

O código Python usando o Agent com Tool Calling. O agente Claude deve ter acesso à ferramenta BingSearchRun.

Mostre onde devo injetar as variáveis de ambiente BING_SUBSCRIPTION_KEY e BING_SEARCH_URL.

Um System Prompt instruindo o Claude: "Você é um assistente de gestão hídrica para a República Democrática do Congo (RDC). Sempre que questionado sobre dados, legislação ou hidrogeologia, use a ferramenta de busca do Bing para encontrar informações recentes e cite a fonte na resposta."

Restrições:

Apenas a rota e o componente. Não crie o servidor FastAPI inteiro do zero.

Mantenha a implementação do agente focada e robusta.

Não há necessidade delangchain nem nada de observabilidade tendo em vista que é um MVP
