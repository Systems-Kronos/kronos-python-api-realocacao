import os
import psycopg2
import psycopg2.extras
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
from redis import Redis
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from bson import ObjectId

load_dotenv("kronos-rpa/.env") 

# --- Configurações iniciais ---
app = FastAPI(
    title="Kronos Realocação API",
    description="Serviço para gerenciamento de realocação e devolução de tarefas.",
    version="1.0.0"
)
hoje = datetime.now().date()

# --- Handlers de Serialização ---

def json_default_handler(obj):
    """Lida com tipos não serializáveis, como ObjectId do MongoDB."""
    if isinstance(obj, ObjectId):
        return str(obj)
    # Garante que a data/hora também é serializável (FastAPI/Starlette já faz isso, mas é bom ter)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


# --- Métodos de Conexão e Lógica de Negócio ---

def get_db_connection():
    try:
        db_url = os.getenv('DATABASE_URL')
        if db_url:
            connection = psycopg2.connect(db_url)
        else:
            connection = psycopg2.connect(
                host=os.getenv('SQL_HOST'),
                user=os.getenv('SQL_USER'),
                password=os.getenv('SQL_PASSWORD'),
                dbname=os.getenv('SQL_DBNAME'),
                port=os.getenv('SQL_PORT', 5432)
            )
        return connection
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return None

def processar_realocacao(usuario_ausente_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False, {"erro": "Falha na conexão com o DB SQL."}
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) 

        # Busca tarefas ativas do usuário ausente e seus substitutos qualificados
        cursor.execute("""
            SELECT
                sub.nCdTarefa,
                sub.nCdUsuarioSubstituto,
                tu.nCdUsuarioOriginal
            FROM fn_busca_substituto(%s) sub
                 JOIN TarefaUsuario tu ON sub.nCdTarefa = tu.nCdTarefa 
            WHERE tu.nCdUsuarioAtuante = %s
        """, (usuario_ausente_id, usuario_ausente_id))
        
        tarefas_a_realocar = cursor.fetchall()
        
        if not tarefas_a_realocar:
            return True, []

        tarefas_realocadas = []
        for tarefa in tarefas_a_realocar:
            tarefa_id = int(tarefa['ncdtarefa'])
            substituto_id = int(tarefa['ncdusuariosubstituto']) if tarefa['ncdusuariosubstituto'] is not None else None
            usuario_original_id = int(tarefa['ncdusuariooriginal'])
            
            if substituto_id:
                cursor.execute("CALL sp_realoca_tarefa(%s, %s, %s)", (substituto_id, tarefa_id, usuario_original_id))

                tarefas_realocadas.append({
                    "nCdTarefa": tarefa_id,
                    "nCdUsuarioOriginal": usuario_original_id,
                    "nCdUsuarioAtuante": usuario_ausente_id,
                    "nCdUsuarioSubstituto": substituto_id,
                    "cRealocacao": True,
                    "dDataExecucao": datetime.now().isoformat()
                })
                # Registra notificação para o substituto
                mensagem = f"Tarefa {tarefa_id} realocada para você temporariamente."
                registra_notificacao(substituto_id, mensagem)
            else:
                tarefas_realocadas.append({
                    "nCdTarefa": tarefa_id,
                    "nCdUsuarioAtuante": usuario_ausente_id,
                    "cMotivo": "Nenhum substituto qualificado encontrado.",
                    "cRealocacao": False,
                    "dDataExecucao": datetime.now().isoformat()
                })
                # Registra notificação para o usuário ausente sobre a falha na realocação
                mensagem = f"Tarefa {tarefa_id} não pôde ser realocada: Nenhum substituto qualificado encontrado."
                registra_notificacao(usuario_ausente_id, mensagem)


        conn.commit() 
        return True, tarefas_realocadas

    except Exception as e:
        if conn:
            conn.rollback() 
        print(f"Erro inesperado durante a realocação SQL: {e}")
        return False, {"erro_sql": str(e)}
    finally:
        if conn:
            conn.close()

def processar_devolucao(usuario_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False, {"erro": "Falha na conexão com o DB SQL."}
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Busca todas as tarefas originais de um usuário, que foram realocadas para outros usuários
        cursor.execute("""
            SELECT nCdTarefa
                 , nCdUsuarioOriginal
                 , nCdUsuarioAtuante
              FROM TarefaUsuario
             WHERE nCdUsuarioOriginal = %s
               AND nCdUsuarioOriginal != nCdUsuarioAtuante
        """, (usuario_id,))
        
        tarefas_a_devolver = cursor.fetchall()
        
        if not tarefas_a_devolver:
            return True, []
        
        cursor.execute("""
            UPDATE TarefaUsuario
               SET nCdUsuarioAtuante = nCdUsuarioOriginal
             WHERE nCdUsuarioOriginal = %s
               AND nCdUsuarioOriginal != nCdUsuarioAtuante
        """, (usuario_id,))

        tarefas_devolvidas = []
        for tarefa in tarefas_a_devolver:
            tarefa_id = int(tarefa['nCdTarefa'])
            
            usuario_atuante_anterior_id = int(tarefa['ncdusuarioatuante']) 
            usuario_original_id = int(tarefa['ncdusuariooriginal'])                     

            tarefas_devolvidas.append({
                "nCdTarefa": tarefa_id,
                "nCdUsuarioAtuanteAnterior": usuario_atuante_anterior_id,
                "nCdUsuarioOriginal": usuario_original_id,
                "nCdUsuarioRetornando": usuario_id,
                "cDevolucao": True,
                "dDataExecucao": datetime.now().isoformat()
            })
        
        # Notifica o usuário que está retornando
        for devolucao in tarefas_devolvidas:
            mensagem = f"Tarefa {devolucao['nCdTarefa']} foi devolvida para você!."
            registra_notificacao(devolucao['nCdUsuarioRetornando'], mensagem)

        conn.commit() 
        return True, tarefas_devolvidas

    except Exception as e:
        if conn:
            conn.rollback() 
        print(f"Erro inesperado durante a devolução SQL: {e}")
        return False, {"erro_sql": str(e)}
    finally:
        if conn:
            conn.close()

def registra_notificacao(usuario_id, mensagem):
    try:
        r = Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT')),
            username=os.getenv('REDIS_USER'),
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True 
        )
        # Ping para garantir a conexão antes de usar
        r.ping() 

        notificacao_id = r.incr(f"usuario:{usuario_id}:notificacao:id")
        notificacao_key = f"usuario:{usuario_id}:notificacao:{notificacao_id}"

        # Atributos da notificação
        agora = datetime.now().isoformat()
        
        r.hset(notificacao_key, mapping={
            "nCdUsuario": usuario_id,
            "cMensagem": mensagem,
            "dCriacao": agora
        })

        r.expire(notificacao_key, 7 * 24 * 3600)  # Expira em 7 dias

        print(f"Notificação registrada para o usuário {usuario_id}: {mensagem}")
    except Exception as e:
        print(f"Erro ao registrar notificação no Redis: {e}")
      
# --- Endpoints da API (FastAPI) ---

@app.post('/realocar-tarefas', tags=["Realocação"], status_code=200,
          summary="Realoca tarefas de um usuário ausente (chamada pelo backend mobile).")
async def realocar_tarefas(nCdUsuario):
    """
    Realiza a realocação imediata de todas as tarefas de um usuário ausente 
    para um substituto qualificado (ou marca como não realocada).
    """
    usuario_ausente_id = nCdUsuario
    
    print(f"Tempo Real: Iniciando realocação para o usuário {usuario_ausente_id}")

    sucesso, realocacoes = processar_realocacao(usuario_ausente_id)
    
    if not sucesso:
        # Lança uma exceção HTTP 500 se houver falha na conexão ou execução SQL
        raise HTTPException(status_code=500, detail={"erro": "Falha na realocação SQL.", "detalhes": realocacoes})
    
    try:
        # Salva o relatório no MongoDB
        mongo_client = MongoClient(os.getenv('MONGODB_URI'))
        mongo_db = mongo_client.get_database('dbKronos')
        relatorios_collection = mongo_db.get_collection('relatorios_realocacao')
        
        if realocacoes:
            # Garante que o insert só ocorre se for uma lista válida de relocações
            if isinstance(realocacoes, list): 
                relatorios_collection.insert_many(realocacoes)
        print("Relatório de realocação salvo no MongoDB.")
    except Exception as e:
        print(f"Erro ao salvar relatório no MongoDB: {e}")
    
    try:
        json_serializable_realocacoes = json.loads(json.dumps(realocacoes, default=json_default_handler))
    except Exception as e:
        # Fallback de segurança caso a serialização falhe
        print(f"Erro fatal na serialização de retorno: {e}")
        json_serializable_realocacoes = [{"erro_serializacao": str(e), "mensagem": "Falha ao preparar relatórios para JSON"}]

    return JSONResponse(content={
        "mensagem": "Realocação de tarefas concluída com sucesso.",
        "detalhes": json_serializable_realocacoes
    }, status_code=200)

@app.post('/processar-ausencias-agendadas', tags=["Agendamento"], status_code=200,
          summary="Processa todas as ausências agendadas para hoje (chamada CRON/Git Action).")
async def processar_ausencias_agendadas():
    # Busca no MongoDB por usuários com ausência agendada para o dia atual e 
    # aciona a lógica de realocação para cada um.
    try:
        print(f"Agendado: Iniciando varredura de faltas para a data: {hoje}")

        mongo_client = MongoClient(os.getenv('MONGODB_URI'))
        mongo_db = mongo_client.get_database('dbKronos')
        calendario_collection = mongo_db.get_collection('calendario')
        relatorios_collection = mongo_db.get_collection('relatorios_realocacao')

        # Busca no MongoDB por faltas agendadas para HOJE.
        ausencias_hoje = calendario_collection.find({
            "bPresenca": False,
            "$expr": {
                "$and": [
                    {"$eq": [{"$dayOfMonth": "$dEvento"}, hoje.day]},
                    {"$eq": [{"$month": "$dEvento"}, hoje.month]},
                    {"$eq": [{"$year": "$dEvento"}, hoje.year]}
                ]
            }
        })

        usuarios_ausentes = [int(doc['nCdUsuario']) for doc in ausencias_hoje if 'nCdUsuario' in doc]
        usuarios_a_processar = list(set(usuarios_ausentes))
        
        relatorio_geral = []

        for user_id in usuarios_a_processar:
            print(f"   > Processando realocação agendada para o usuário {user_id}")
            sucesso, realocacoes = processar_realocacao(user_id)
            
            if sucesso and realocacoes:
                if isinstance(realocacoes, list): 
                    relatorios_collection.insert_many(realocacoes)
                    relatorio_geral.extend(realocacoes)
        
        print(f"Agendado: Processamento de {len(usuarios_a_processar)} usuários concluído.")
        
        json_serializable_relatorio = json.loads(json.dumps(relatorio_geral, default=json_default_handler))
        
        return JSONResponse(content={
            "mensagem": "Processamento agendado concluído com sucesso.",
            "usuarios_processados": len(usuarios_a_processar),
            "total_tarefas_realocadas": len(json_serializable_relatorio)
        }, status_code=200)

    except Exception as e:
        print(f"Erro no processamento agendado: {e}")
        raise HTTPException(status_code=500, detail={"erro": f"Erro no processamento agendado: {e}"})

@app.post('/devolucao-tarefas', tags=["Agendamento"], status_code=200,
          summary="Devolve tarefas a usuários que retornaram de falta (chamada CRON/Git Action).")
async def devolucao_tarefa():
    # Identifica usuários que estavam ausentes no dia anterior e que não agendaram falta 
    # para o dia atual, devolvendo suas tarefas originais.

    try:
        print(f"Agendado: Iniciando varredura de presenças para a data: {hoje}")

        mongo_client = MongoClient(os.getenv('MONGODB_URI'))
        mongo_db = mongo_client.get_database('dbKronos')
        calendario_collection = mongo_db.get_collection('calendario')
        relatorios_collection = mongo_db.get_collection('relatorios_realocacao')

        # Busca no MongoDB por recém-presentes
        recem_presentes = calendario_collection.aggregate([
            { "$match": {
                "bPresenca": False,
                "$expr": {
                    "$and": [
                        { "$eq": [{ "$dayOfMonth": "$dEvento"}, hoje.day - 1]},
                        { "$eq": [{ "$month": "$dEvento"}, hoje.month]},
                        { "$eq": [{ "$year": "$dEvento"}, hoje.year]},
                    ]
                }
            }},
            {"$lookup": {
                "from": "calendario",
                "let": {"user": "$nCdUsuario"},
                "pipeline": [
                    {"$match": {
                        "$expr": {
                            "$and": [
                                {"$eq": ["$nCdUsuario", "$$user"]},
                                {"$eq": [{"$dayOfMonth": "$dEvento"}, hoje.day]},
                                {"$eq": [{"$month": "$dEvento"}, hoje.month]},
                                {"$eq": [{"$year": "$dEvento"}, hoje.year]},
                                {"$eq": ["$bPresenca", False]}
                            ]
                        }
                    }}
                ],
                "as": "faltasHoje"
            }},
            {"$match": {
                "faltasHoje": {"$size": 0}
            }},
            {"$project": {
                "_id": 0,
                "nCdUsuario": 1
            }}
        ])

        usuarios_recem_presentes = [int(doc['nCdUsuario']) for doc in recem_presentes if 'nCdUsuario' in doc]
        usuarios_a_processar = list(set(usuarios_recem_presentes)) 

        relatorio_geral = []
        for user_id in usuarios_a_processar:
            print(f"   > Processando devolução para o usuário {user_id}")
            sucesso, devolucoes = processar_devolucao(user_id)
            
            if sucesso and devolucoes:
                if isinstance(devolucoes, list):
                    relatorios_collection.insert_many(devolucoes)
                    relatorio_geral.extend(devolucoes)
        
        json_serializable_relatorio = json.loads(json.dumps(relatorio_geral, default=json_default_handler))
        
        return JSONResponse(content={
            "mensagem": "Processamento de devolução concluído com sucesso.",
            "usuarios_processados": len(usuarios_a_processar),
            "total_tarefas_devolvidas": len(json_serializable_relatorio)
        }, status_code=200)

    except Exception as e:
        print(f"Erro no processamento de devolução: {e}")
        raise HTTPException(status_code=500, detail={"erro": f"Erro no processamento de devolução: {e}"})

# Configuração para rodar localmente com uvicorn
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
