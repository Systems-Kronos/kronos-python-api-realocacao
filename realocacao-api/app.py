import os
import psycopg2
import psycopg2.extras
from pymongo import MongoClient
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime

load_dotenv("kronos-rpa/.env") 

app = Flask(__name__)

def get_db_connection():
    try:
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
                    "nCdUsuarioSubstituto": substituto_id,
                    "cRealocacao": True,
                    "dDataExecucao": datetime.now().isoformat()
                })
            else:
                tarefas_realocadas.append({
                    "nCdTarefa": tarefa_id,
                    "cMotivo": "Nenhum substituto qualificado encontrado.",
                    "cRealocacao": False,
                    "dDataExecucao": datetime.now().isoformat()
                })
        
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

# --- Endpoints da API ---

@app.route('/realocar-tarefas', methods=['POST'])
def realocar_tarefas():
    """
    ENDPOINT 1: Recebe o webhook da Trigger do MongoDB (Realocação em Tempo Real).
    """
    try:
        data = request.get_json()
        usuario_ausente_id = data.get('nCdUsuario')
        
        if not usuario_ausente_id:
            return jsonify({"erro": "ID do usuário ausente na requisição"}), 400

        print(f"Tempo Real: Iniciando realocação para o usuário {usuario_ausente_id}")

        sucesso, realocacoes = processar_realocacao(usuario_ausente_id)
        
        if not sucesso:
            return jsonify({"erro": "Falha na realocação SQL.", "detalhes": realocacoes}), 500
        
        try:
            mongo_client = MongoClient(os.getenv('MONGODB_URI'))
            mongo_db = mongo_client.get_database('dbKronos')
            relatorios_collection = mongo_db.get_collection('relatorios_realocacao')
            
            if realocacoes: 
                relatorios_collection.insert_many(realocacoes)
            print("Relatório de realocação salvo no MongoDB.")
        except Exception as e:
            print(f"Erro ao salvar relatório no MongoDB: {e}")

        return jsonify({
            "mensagem": "Realocação de tarefas concluída com sucesso.",
            "detalhes": realocacoes
        }), 200

    except Exception as e:
        print(f"Erro inesperado no endpoint /realocar-tarefas: {e}")
        return jsonify({"erro": "Ocorreu um erro interno no servidor."}), 500


@app.route('/processar-ausencias-agendadas', methods=['POST'])
def processar_ausencias_agendadas():
    try:
        hoje = datetime.now().date()
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
        usuarios_a_processar = list(set(usuarios_ausentes)) # Processa cada usuário ausente apenas uma vez
        
        relatorio_geral = []

        for user_id in usuarios_a_processar:
            print(f"  > Processando realocação agendada para o usuário {user_id}")
            sucesso, realocacoes = processar_realocacao(user_id)
            
            if sucesso and realocacoes:
                relatorios_collection.insert_many(realocacoes)
                relatorio_geral.extend(realocacoes)
        
        print(f"Agendado: Processamento de {len(usuarios_a_processar)} usuários concluído.")
        return jsonify({
            "mensagem": "Processamento agendado concluído com sucesso.",
            "usuarios_processados": len(usuarios_a_processar),
            "total_tarefas_realocadas": len(relatorio_geral)
        }), 200

    except Exception as e:
        print(f"Erro no processamento agendado: {e}")
        return jsonify({"erro": f"Erro no processamento agendado: {e}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)