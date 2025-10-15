## **API de Realocação**

API desenvolvida em Python (Flask) para gerenciar a realocação automática de tarefas no sistema Kronos em casos de ausência de usuários. O serviço busca substitutos qualificados para tarefas ativas e realoca as pendências, além de gerenciar a devolução de tarefas quando o usuário original retorna.

### 📝 Descrição

Este microsserviço é o motor de realocação de tarefas do sistema Kronos. Ele fornece endpoints para:

1.  **Realocação imediata:** Acionada em tempo real, por exemplo, após a aprovação de uma licença.
2.  **Processamento agendado:** Executado diariamente para processar ausências e presenças (devolução de tarefas) registradas no calendário do sistema.

A API se conecta a diferentes bancos de dados para buscar dados transacionais (PostgreSQL), armazenar o calendário de ausências/presenças (MongoDB) e registrar notificações para os usuários (Redis).

### 🛠️ Tecnologias Principais

* **Linguagem:** Python
* **Framework Web:** Flask
* **Banco de Dados Transacional:** PostgreSQL (via `psycopg2-binary`)
* **Banco de Dados NoSQL/Calendário:** MongoDB (via `pymongo`)
* **Fila/Notificações:** Redis
* **Servidor Web:** Gunicorn (para produção)

### 💡 Funcionalidades e Endpoints

| Endpoint | Método | Descrição |
| :--- | :--- | :--- |
| `/realocar-tarefas` | `POST` | Realiza a realocação de tarefas em **tempo real** para um usuário ausente específico, buscando substitutos qualificados no PostgreSQL e registrando o relatório no MongoDB. |
| `/processar-ausencias-agendadas` | `POST` | Processa todas as ausências agendadas para o dia atual no MongoDB, acionando a lógica de realocação para cada usuário ausente. **Ideal para CRON jobs.** |
| `/devolucao-tarefas` | `POST` | Identifica usuários que estavam ausentes no dia anterior, mas não agendaram falta para hoje, e devolve as tarefas ao usuário original no PostgreSQL. |

### ⚙️ Configuração e Execução Local

#### Pré-requisitos
* Python 3.x
* Acesso e credenciais para instâncias de PostgreSQL, MongoDB e Redis.

#### 1. Instalação de Dependências

```bash
# Navegue até o diretório realocacao-api
cd realocacao-api

# Instale as dependências
pip install -r requirements.txt
```

#### 2. Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto (`kronos-python-api-realocacao/`) com as seguintes variáveis (conforme as configurações de conexão em `app.py`):

```
# Variáveis do arquivo de ambiente (load_dotenv("kronos-rpa/.env"))
# OBS: O caminho usado no app.py é 'kronos-rpa/.env'. Ajuste se o arquivo .env estiver na raiz do projeto.

# PostgreSQL
SQL_HOST=seuhost.postgres.com
SQL_USER=seu_usuario
SQL_PASSWORD=sua_senha
SQL_DBNAME=seu_banco
SQL_PORT=5432

# MongoDB
MONGODB_URI=mongodb://seu_usuario:sua_senha@seuhost.mongo.com:27017/dbKronos

# Redis
REDIS_HOST=seuhost.redis.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_USER=seu_usuario_redis
REDIS_PASSWORD=sua_senha_redis
```

#### 3. Execução

Para desenvolvimento, você pode executar o arquivo diretamente:

```bash
python realocacao-api/app.py
```

Para produção ou um ambiente mais robusto, utilize o Gunicorn, conforme a configuração de deploy:

```bash
gunicorn --bind 0.0.0.0:10000 --workers 4 --timeout 300 realocacao_api:app
```

### 🚀 Deploy (Render)

A aplicação é configurada para deploy como um serviço web no **Render**, utilizando o Gunicorn.

* **Nome do Serviço:** `kronos-api-realocacao`
* **Comando de Build:** `pip install -r requirements.txt`
* **Comando de Início:** `gunicorn --bind 0.0.0.0:10000 --workers 4 --timeout 300 realocacao_api:app`

### ⏰ Processamento Agendado (GitHub Actions)

O projeto inclui um fluxo de trabalho (Workflow) do GitHub Actions para garantir o processamento diário das ausências agendadas.

* **Frequência:** Diariamente às **03:00 UTC** (`cron: '0 3 * * *'`)
* **Ação:** Chama o endpoint `/processar-ausencias-agendadas` da API do Render (utilizando a variável de segredo `RENDER_API_URL`).

### ⚖️ Licença

Este projeto está sob a licença **MIT License**.

Copyright (c) 2025 Systems Kronos