# kronos-python-api-realocacao

## Índice

- [📓 Sobre](#-sobre)
- [🚀 Tecnologias](#-tecnologias)
- [✨ Funcionalidades](#-funcionalidades)
- [⚙️ Instalação](#-instalação)
- [⏰ Processamento Agendado (GitHub Actions)](#-processamento-agendado-(-gitHub-actions-))
- [📄 Licença](#-licença)
- [💻 Autores](#-autores)

</br>

## 📓 Sobre

API desenvolvida em Python (Flask) para gerenciar a realocação automática de tarefas no sistema Kronos em casos de ausência de usuários. O serviço busca substitutos qualificados para tarefas ativas e realoca as pendências, além de gerenciar a devolução de tarefas quando o usuário original retorna.

</br>

## 🚀 Tecnologias

* Python
* Flask
* PostgreSQL (via `psycopg2-binary`)
* MongoDB (via `pymongo`)
* Redis
* Gunicorn (para produção)

</br>

## ✨ Funcionalidades

- Realiza a realocação de tarefas em tempo real para um usuário ausente específico, buscando substitutos qualificados no PostgreSQL e registrando o relatório no MongoDB;
- Processa todas as ausências agendadas para o dia atual no MongoDB, acionando a lógica de realocação para cada usuário ausente.Ideal para CRON jobs;
- Identifica usuários que estavam ausentes no dia anterior e devolve as tarefas ao titular original no PostgreSQL.

</br>

## ⚙️ Instalação

É necessário ter o Python (versão 3 ou superior) e acesso e credenciais para instâncias de PostgreSQL, MongoDB e Redis.

```
# clonar o repositório
git clone https://github.com/Systems-Kronos/kronos-python-api-realocacao.git

# entrar no diretório
cd kronos-python-api-realocacao

# instalar dependências  
kronos-python-api-realocacao

# configure as variáveis de ambiente
# crie um arquivo .env na raiz do projeto com o seguinte conteúdo:
SQL_HOST=seuhost.postgres.com
SQL_USER=seu_usuario
SQL_PASSWORD=sua_senha
SQL_DBNAME=seu_banco
SQL_PORT=5432
MONGODB_URI=mongodb://seu_usuario:sua_senha@seuhost.mongo.com:27017/dbKronos
REDIS_HOST=seuhost.redis.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_USER=seu_usuario_redis
REDIS_PASSWORD=sua_senha_redis

# execução - modo desenvolvimento
python realocacao-api/app.py
# execução - modo produção
gunicorn --bind 0.0.0.0:10000 --workers 4 --timeout 300 realocacao_api:app

```

</br>

## ⏰ Processamento Agendado (GitHub Actions)

O projeto inclui um fluxo de trabalho (Workflow) do GitHub Actions para garantir o processamento diário das ausências agendadas.

* **Frequência:** Diariamente às **06:00 UTC** (`cron: '0 6 * * *'`)
* **Ação:** Chama os endpoints `/processar-ausencias-agendadas` e `/devolucao-tarefas` da API do Render (utilizando as variáveis de segredo `RENDER_API_REALOCACAO_URL` e `RENDER_API_DEVOLUCAO_URL`).

</br>

## 📄 Licença

Este projeto está licenciado sob a licença MIT — veja o arquivo LICENSE para mais detalhes.

</br>

## 💻 Autores

- [Theo Martins](https://github.com/TheoMGtech)
