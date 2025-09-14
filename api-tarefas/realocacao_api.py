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
            port=os.getenv('SQL_PORT', 5432)q
        )
        return connection
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return None

@app.route('/realocar-tarefas', methods=['POST'])
def realocar_tarefas():
    conn = None
    try:
        data = request.get_json()
        if not data or 'nCdUsuario' not in data:
            return jsonify({"erro": "ID do usuário ausente na requisição"}), 400

        usuario_ausente_id = data['nCdUsuario']
        print(f"Iniciando realocação de tarefas para o usuário {usuario_ausente_id}")

        conn = get_db_connection()
        if not conn:
            return jsonify({"erro": "Não foi possível conectar ao banco de dados."}), 500
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute("""
            SELECT
                sub.nCdTarefa,
                sub.nCdUsuarioSubstituto,
            FROM fn_busca_substituto(%s) sub
        """, (usuario_ausente_id,))
        tarefas_a_realocar = cursor.fetchall()
        
        if not tarefas_a_realocar:
            print(f"Nenhuma tarefa em andamento encontrada para o usuário {usuario_ausente_id}")
            return jsonify({"mensagem": "Nenhuma tarefa em andamento encontrada."}), 200

        print(f"Encontradas {len(tarefas_a_realocar)} tarefas para realocar.")
        tarefas_realocadas = []
        for tarefa in tarefas_a_realocar:
            tarefa_id = int(tarefa['ncdtarefa'])
            substituto_id = int(tarefa['ncdusuariosubstituto']) if tarefa['ncdusuariosubstituto'] is not None else None  
            
            if substituto_id:
                cursor.execute("CALL sp_realoca_tarefa(%s, %s, %s)", (substituto_id, tarefa_id, usuario_ausente_id))
                tarefas_realocadas.append({
                    "nCdTarefa": tarefa_id,
                    "nCdUsuarioOriginal": int(usuario_ausente_id),
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
        
        print(f"Realocação concluída. Detalhes: {tarefas_realocadas}")
        # Adiciona detalhes da API no MongoDB
        try:
            mongo_client = MongoClient(os.getenv('MONGODB_URI'))
            mongo_db = mongo_client.get_database('dbKronos')
            relatorios_collection = mongo_db.get_collection('relatorios_realocacao')
            
            relatorios_collection.insert_many(tarefas_realocadas)

            print("Relatório de realocação salvo no MongoDB.")
        except Exception as e:
            print(f"Erro ao salvar relatório no MongoDB: {e}")

        return jsonify({"mensagem": "Realocação de tarefas concluída com sucesso."}), 200
    except Exception as e:
        if conn:
            conn.rollback() 
        print(f"Erro inesperado: {e}")
        return jsonify({"erro": "Ocorreu um erro interno no servidor."}), 500
    finally:
        if conn:
            cursor.close()
            conn.close()
            print("Conexão com o banco de dados fechada.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
