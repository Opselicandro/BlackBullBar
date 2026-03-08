from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os
import logging

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'blackbull-bar-management-secret'

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'blackbull_bar.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabela de Produtos
    c.execute('''CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        preco_compra REAL NOT NULL,
        preco_venda REAL NOT NULL,
        quantidade INTEGER DEFAULT 0,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tabela de Vendedores
    c.execute('''CREATE TABLE IF NOT EXISTS vendedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        usuario TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        ativo BOOLEAN DEFAULT 1,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tabela de Sessões de Venda (NOVA)
    c.execute('''CREATE TABLE IF NOT EXISTS sessoes_venda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendedor_id INTEGER NOT NULL,
        data_sessao DATE NOT NULL,
        hora_inicio TIME NOT NULL,
        hora_encerramento TIME,
        status TEXT DEFAULT 'ativa',
        total_vendido REAL DEFAULT 0,
        total_dinheiro REAL DEFAULT 0,
        total_banco REAL DEFAULT 0,
        total_credito REAL DEFAULT 0,
        observacoes TEXT,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        data_encerramento TIMESTAMP,
        FOREIGN KEY (vendedor_id) REFERENCES vendedores(id),
        CHECK (status IN ('ativa', 'encerrada'))
    )''')
    
    # Tabela de Vendas (ATUALIZADA - adicionar sessao_id)
    c.execute('''CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendedor_id INTEGER NOT NULL,
        sessao_id INTEGER,
        tipo_pagamento TEXT NOT NULL,
        valor_total REAL NOT NULL,
        cliente_nome TEXT,
        cancelada BOOLEAN DEFAULT 0,
        data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vendedor_id) REFERENCES vendedores(id),
        FOREIGN KEY (sessao_id) REFERENCES sessoes_venda(id)
    )''')
    
    # Tabela de Itens de Venda
    c.execute('''CREATE TABLE IF NOT EXISTS itens_venda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venda_id INTEGER NOT NULL,
        produto_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        preco_unitario REAL NOT NULL,
        subtotal REAL NOT NULL,
        FOREIGN KEY (venda_id) REFERENCES vendas(id),
        FOREIGN KEY (produto_id) REFERENCES produtos(id)
    )''')
    
    # Tabela de Dívidas
    c.execute('''CREATE TABLE IF NOT EXISTS dividas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venda_id INTEGER NOT NULL,
        cliente_nome TEXT NOT NULL,
        valor_total REAL NOT NULL,
        valor_pago REAL DEFAULT 0,
        status TEXT DEFAULT 'pendente',
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (venda_id) REFERENCES vendas(id)
    )''')
    
    # Tabela de Resumos de Sessão (NOVA)
    c.execute('''CREATE TABLE IF NOT EXISTS resumos_sessao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sessao_id INTEGER NOT NULL UNIQUE,
        vendedor_id INTEGER NOT NULL,
        data_sessao DATE NOT NULL,
        hora_inicio TIME NOT NULL,
        hora_encerramento TIME NOT NULL,
        total_vendido REAL NOT NULL,
        total_dinheiro REAL NOT NULL,
        total_banco REAL NOT NULL,
        total_credito REAL NOT NULL,
        quantidade_vendas INTEGER NOT NULL,
        ticket_medio REAL NOT NULL,
        data_geracao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sessao_id) REFERENCES sessoes_venda(id),
        FOREIGN KEY (vendedor_id) REFERENCES vendedores(id)
    )''')
    
    # Tabela de Logs de Sessão (NOVA)
    c.execute('''CREATE TABLE IF NOT EXISTS logs_sessao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sessao_id INTEGER NOT NULL,
        vendedor_id INTEGER NOT NULL,
        acao TEXT NOT NULL,
        detalhes TEXT,
        data_log TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sessao_id) REFERENCES sessoes_venda(id),
        FOREIGN KEY (vendedor_id) REFERENCES vendedores(id)
    )''')
    
    # Inserir vendedores padrão
    c.execute("SELECT COUNT(*) FROM vendedores")
    if c.fetchone()[0] == 0:
        vendedores_padrao = [
            ('Vendedor 1', 'vendedor1', 'vendedor'),
            ('Vendedor 2', 'vendedor2', 'vendedor'),
            ('Vendedor 3', 'vendedor3', 'vendedor')
        ]
        c.executemany("INSERT INTO vendedores (nome, usuario, senha) VALUES (?, ?, ?)", vendedores_padrao)
    
    conn.commit()
    conn.close()

init_db()

# ============= AUTENTICAÇÃO =============

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    usuario = data.get('usuario')
    senha = data.get('senha')
    
    if usuario == 'admin' and senha == 'admin123':
        return jsonify({
            'success': True,
            'tipo': 'admin',
            'nome': 'Administrador'
        })
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM vendedores WHERE usuario=? AND senha=? AND ativo=1", (usuario, senha))
    vendedor = c.fetchone()
    conn.close()
    
    if vendedor:
        return jsonify({
            'success': True,
            'tipo': 'vendedor',
            'id': vendedor['id'],
            'nome': vendedor['nome']
        })
    
    return jsonify({'success': False, 'message': 'Usuário ou senha incorretos'}), 401

# ============= SESSÕES DE VENDA =============

@app.route('/api/sessoes/iniciar', methods=['POST'])
def iniciar_sessao():
    """Inicia uma nova sessão de venda para um vendedor"""
    data = request.json
    vendedor_id = data.get('vendedor_id')
    
    if not vendedor_id:
        return jsonify({'success': False, 'message': 'Vendedor não informado'}), 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verificar se já existe sessão ativa para este vendedor
        c.execute('''SELECT id FROM sessoes_venda 
                     WHERE vendedor_id = ? AND status = 'ativa' ''', (vendedor_id,))
        sessao_ativa = c.fetchone()
        
        if sessao_ativa:
            conn.close()
            return jsonify({
                'success': True,
                'message': 'Sessão já está ativa',
                'sessao_id': sessao_ativa[0]
            })
        
        # Criar nova sessão
        agora = datetime.now()
        data_sessao = agora.strftime('%Y-%m-%d')
        hora_inicio = agora.strftime('%H:%M:%S')
        
        c.execute('''INSERT INTO sessoes_venda 
                     (vendedor_id, data_sessao, hora_inicio, status)
                     VALUES (?, ?, ?, 'ativa')''',
                  (vendedor_id, data_sessao, hora_inicio))
        
        sessao_id = c.lastrowid
        
        # Registrar log
        c.execute('''INSERT INTO logs_sessao 
                     (sessao_id, vendedor_id, acao, detalhes)
                     VALUES (?, ?, 'INICIO', ?)''',
                  (sessao_id, vendedor_id, f'Sessão iniciada em {data_sessao} às {hora_inicio}'))
        
        conn.commit()
        conn.close()
        
        logger.info(f'Sessão {sessao_id} iniciada para vendedor {vendedor_id}')
        
        return jsonify({
            'success': True,
            'message': 'Sessão iniciada com sucesso',
            'sessao_id': sessao_id,
            'data_sessao': data_sessao,
            'hora_inicio': hora_inicio
        })
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f'Erro ao iniciar sessão: {str(e)}')
        return jsonify({'success': False, 'message': f'Erro ao iniciar sessão: {str(e)}'}), 500

@app.route('/api/sessoes/encerrar', methods=['POST'])
def encerrar_sessao():
    """Encerra sessão ativa do vendedor e salva resumo na gestão"""
    data = request.json
    vendedor_id = data.get('vendedor_id')
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Buscar sessão ativa
        c.execute('''SELECT * FROM sessoes_venda 
                     WHERE vendedor_id = ? AND status = 'ativa' 
                     ORDER BY id DESC LIMIT 1''', (vendedor_id,))
        sessao = c.fetchone()
        
        if not sessao:
            conn.close()
            return jsonify({'success': False, 'message': 'Nenhuma sessão ativa encontrada'}), 404
        
        sessao_id = sessao['id']
        data_sessao = sessao['data_sessao']
        hora_inicio = sessao['hora_inicio']
        
        # Buscar dados do vendedor
        c.execute('SELECT nome FROM vendedores WHERE id = ?', (vendedor_id,))
        vendedor = c.fetchone()
        vendedor_nome = vendedor['nome'] if vendedor else 'Desconhecido'
        
        # Calcular totais da sessão
        c.execute('''SELECT 
                        COUNT(*) as total_vendas,
                        SUM(valor_total) as total_vendido,
                        SUM(CASE WHEN tipo_pagamento = 'dinheiro' THEN valor_total ELSE 0 END) as total_cash,
                        SUM(CASE WHEN tipo_pagamento = 'banco' THEN valor_total ELSE 0 END) as total_banco,
                        SUM(CASE WHEN tipo_pagamento = 'credito' THEN valor_total ELSE 0 END) as total_credito
                     FROM vendas 
                     WHERE sessao_id = ? AND cancelada = 0''', (sessao_id,))
        
        totais = c.fetchone()
        
        total_vendas = totais['total_vendas'] or 0
        total_vendido = totais['total_vendido'] or 0.0
        total_cash = totais['total_cash'] or 0.0
        total_banco = totais['total_banco'] or 0.0
        total_credito = totais['total_credito'] or 0.0
        
        # IMPORTANTE: Crédito é registrado como NEGATIVO (é dívida, não dinheiro recebido)
        total_dividas_negativo = -total_credito  # Valor negativo
        
        # Global vendido = cash + banco (crédito não entra, é dívida)
        global_vendido = total_cash + total_banco
        
        # Hora de encerramento
        agora = datetime.now()
        hora_fecho = agora.strftime('%H:%M:%S')
        
        # 1. SALVAR NA GESTÃO
        print(f"DEBUG: Salvando turno na gestão - Vendedor {vendedor_nome}")
        c.execute('''INSERT INTO gestao_turnos 
                     (vendedor_id, vendedor_nome, data, hora_abertura, hora_fecho,
                      total_vendido_cash, total_vendido_banco, total_dividas, global_vendido,
                      quantidade_vendas, sessao_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (vendedor_id, vendedor_nome, data_sessao, hora_inicio, hora_fecho,
                   total_cash, total_banco, total_dividas_negativo, global_vendido,
                   total_vendas, sessao_id))
        
        gestao_id = c.lastrowid
        print(f"DEBUG: Turno salvo na gestão com ID {gestao_id}")
        
        # 2. ATUALIZAR SESSÃO COMO ENCERRADA
        c.execute('''UPDATE sessoes_venda 
                     SET status = 'encerrada',
                         hora_encerramento = ?,
                         total_vendido = ?,
                         total_dinheiro = ?,
                         total_banco = ?,
                         total_credito = ?
                     WHERE id = ?''',
                  (hora_fecho, total_vendido, total_cash, total_banco, total_credito, sessao_id))
        
        # 3. SALVAR RESUMO (mantém compatibilidade)
        c.execute('''INSERT INTO resumos_sessao 
                     (sessao_id, vendedor_id, data_sessao, hora_inicio, hora_encerramento,
                      total_vendido, total_dinheiro, total_banco, total_credito,
                      quantidade_vendas, ticket_medio)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (sessao_id, vendedor_id, data_sessao, hora_inicio, hora_fecho,
                   total_vendido, total_cash, total_banco, total_credito,
                   total_vendas, total_vendido / total_vendas if total_vendas > 0 else 0))
        
        # 4. LIMPAR HISTÓRICO DE VENDAS (MANTENDO DÍVIDAS!)
        print(f"DEBUG: Limpando {total_vendas} vendas do histórico...")
        
        # 4.1 Primeiro, limpar itens_venda
        c.execute('DELETE FROM itens_venda WHERE venda_id IN (SELECT id FROM vendas WHERE sessao_id = ?)', 
                  (sessao_id,))
        
        # 4.2 Limpar APENAS vendas que NÃO são crédito (dívidas)
        # Vendas de dinheiro e banco são limpas
        # Vendas de crédito PERMANECEM para controle de dívidas
        c.execute('''DELETE FROM vendas 
                     WHERE sessao_id = ? 
                     AND tipo_pagamento IN ('dinheiro', 'banco')''', 
                  (sessao_id,))
        
        # Contar quantas vendas de crédito foram mantidas
        c.execute('''SELECT COUNT(*) FROM vendas 
                     WHERE sessao_id = ? AND tipo_pagamento = 'credito' ''', 
                  (sessao_id,))
        vendas_credito_mantidas = c.fetchone()[0]
        
        print(f"DEBUG: Histórico limpo! {vendas_credito_mantidas} vendas de crédito mantidas para controle de dívidas.")
        
        # 5. LOG
        c.execute('''INSERT INTO logs_sessao (sessao_id, vendedor_id, acao, detalhes)
                     VALUES (?, ?, 'ENCERRAMENTO', ?)''',
                  (sessao_id, vendedor_id, 
                   f'Turno encerrado. Total: Kz {total_vendido:.2f}. Histórico limpo.'))
        
        conn.commit()
        
        # Preparar resumo para retorno
        resumo = {
            'sessao_id': sessao_id,
            'data': data_sessao,
            'hora_inicio': hora_inicio,
            'hora_encerramento': hora_fecho,
            'total_vendas': total_vendas,
            'total_vendido': float(total_vendido),
            'total_cash': float(total_cash),
            'total_banco': float(total_banco),
            'total_credito': float(total_credito),
            'total_dividas_negativo': float(total_dividas_negativo),
            'global_vendido': float(global_vendido),
            'ticket_medio': float(total_vendido / total_vendas if total_vendas > 0 else 0),
            'gestao_id': gestao_id
        }
        
        conn.close()
        
        logger.info(f'Turno encerrado - Vendedor: {vendedor_id}, Total: Kz {total_vendido:.2f}, Gestão ID: {gestao_id}')
        
        return jsonify({
            'success': True,
            'resumo': resumo,
            'message': f'✅ Turno encerrado!\n\nResumo salvo na Gestão.\nHistórico de vendas limpo.'
        })
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f'Erro ao encerrar sessão: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/sessoes/ativa', methods=['GET'])
def obter_sessao_ativa():
    """Obtém a sessão ativa de um vendedor"""
    vendedor_id = request.args.get('vendedor_id', type=int)
    
    if not vendedor_id:
        return jsonify({'success': False, 'message': 'Vendedor não informado'}), 400
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''SELECT s.*, 
                    COUNT(v.id) as vendas_realizadas,
                    COALESCE(SUM(CASE WHEN v.cancelada = 0 THEN v.valor_total ELSE 0 END), 0) as total_atual
                 FROM sessoes_venda s
                 LEFT JOIN vendas v ON s.id = v.sessao_id
                 WHERE s.vendedor_id = ? AND s.status = 'ativa'
                 GROUP BY s.id
                 ORDER BY s.id DESC LIMIT 1''', (vendedor_id,))
    
    sessao = c.fetchone()
    conn.close()
    
    if sessao:
        return jsonify({
            'success': True,
            'sessao': dict(sessao)
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Nenhuma sessão ativa'
        })

@app.route('/api/sessoes/resumo/<int:sessao_id>', methods=['GET'])
def obter_resumo_sessao(sessao_id):
    """Obtém o resumo completo de uma sessão específica"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''SELECT r.*, v.nome as vendedor_nome
                 FROM resumos_sessao r
                 JOIN vendedores v ON r.vendedor_id = v.id
                 WHERE r.sessao_id = ?''', (sessao_id,))
    
    resumo = c.fetchone()
    conn.close()
    
    if resumo:
        return jsonify({
            'success': True,
            'resumo': dict(resumo)
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Resumo não encontrado'
        }), 404

# ============= PRODUTOS =============

@app.route('/api/produtos', methods=['GET'])
def get_produtos():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM produtos ORDER BY nome")
    produtos = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(produtos)

@app.route('/api/produtos', methods=['POST'])
def add_produto():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO produtos (nome, preco_compra, preco_venda, quantidade)
                 VALUES (?, ?, ?, ?)''',
              (data['nome'], data['preco_compra'], data['preco_venda'], data['quantidade']))
    conn.commit()
    produto_id = c.lastrowid
    conn.close()
    return jsonify({'id': produto_id, 'message': 'Produto adicionado com sucesso!'})

@app.route('/api/produtos/<int:id>', methods=['PUT'])
def update_produto(id):
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE produtos 
                 SET nome=?, preco_compra=?, preco_venda=?, quantidade=?
                 WHERE id=?''',
              (data['nome'], data['preco_compra'], data['preco_venda'], data['quantidade'], id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Produto atualizado com sucesso!'})

@app.route('/api/produtos/<int:id>/adicionar-quantidade', methods=['POST'])
def adicionar_quantidade(id):
    data = request.json
    quantidade = data.get('quantidade', 0)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE produtos SET quantidade = quantidade + ? WHERE id = ?', (quantidade, id))
    conn.commit()
    conn.close()
    return jsonify({'message': f'{quantidade} unidades adicionadas ao estoque!'})

@app.route('/api/produtos/<int:id>', methods=['DELETE'])
def delete_produto(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM produtos WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Produto deletado com sucesso!'})

@app.route('/api/produtos/resumo', methods=['GET'])
def get_resumo_produtos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT 
                    SUM(preco_compra * quantidade) as custo_total,
                    SUM(preco_venda * quantidade) as venda_total,
                    COUNT(*) as total_produtos
                 FROM produtos''')
    resumo = c.fetchone()
    conn.close()
    return jsonify({
        'custo_total': resumo[0] or 0,
        'venda_total': resumo[1] or 0,
        'total_produtos': resumo[2] or 0,
        'lucro_potencial': (resumo[1] or 0) - (resumo[0] or 0)
    })

# ============= VENDEDORES =============

@app.route('/api/vendedores', methods=['GET'])
def get_vendedores():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, nome, usuario FROM vendedores WHERE ativo=1 ORDER BY nome")
    vendedores = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(vendedores)

@app.route('/api/vendedores/<int:id>', methods=['PUT'])
def update_vendedor(id):
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if data.get('senha'):
        c.execute('UPDATE vendedores SET nome=?, senha=? WHERE id=?',
                  (data['nome'], data['senha'], id))
    else:
        c.execute('UPDATE vendedores SET nome=? WHERE id=?',
                  (data['nome'], id))
    
    conn.commit()
    conn.close()
    return jsonify({'message': 'Vendedor atualizado com sucesso!'})

# ============= VENDAS =============

@app.route('/api/vendas', methods=['POST'])
def criar_venda():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        vendedor_id = data['vendedor_id']
        
        # Verificar se é admin
        c.execute('SELECT usuario FROM vendedores WHERE id = ?', (vendedor_id,))
        vendedor_row = c.fetchone()
        is_admin = vendedor_row and vendedor_row[0] == 'admin'
        
        if is_admin:
            # Admin não precisa de sessão
            sessao_id = None
            print(f"DEBUG: Venda de ADMIN - sem requisito de turno")
        else:
            # SEGURANÇA: Vendedores precisam de sessão ativa
            c.execute('''SELECT id, status FROM sessoes_venda 
                         WHERE vendedor_id = ? AND status = 'ativa' 
                         ORDER BY id DESC LIMIT 1''', (vendedor_id,))
            sessao = c.fetchone()
            
            if not sessao:
                # BLOQUEIO: Não permitir venda sem turno iniciado
                conn.close()
                logger.warning(f'Tentativa de venda sem turno ativo - Vendedor: {vendedor_id}')
                return jsonify({
                    'success': False,
                    'error': 'Turno não iniciado',
                    'message': '⚠️ Você precisa INICIAR O TURNO antes de fazer vendas!'
                }), 403
            
            sessao_id = sessao[0]
            print(f"DEBUG: Venda de vendedor {vendedor_id} - sessão {sessao_id}")
        
        # Criar venda
        c.execute('''INSERT INTO vendas (vendedor_id, sessao_id, tipo_pagamento, valor_total, cliente_nome, cancelada)
                     VALUES (?, ?, ?, ?, ?, 0)''',
                  (vendedor_id, sessao_id, data['tipo_pagamento'], data['valor_total'], 
                   data.get('cliente_nome', None)))
        venda_id = c.lastrowid
        
        # Adicionar itens
        for item in data['itens']:
            c.execute('''INSERT INTO itens_venda (venda_id, produto_id, quantidade, preco_unitario, subtotal)
                         VALUES (?, ?, ?, ?, ?)''',
                      (venda_id, item['produto_id'], item['quantidade'], 
                       item['preco_unitario'], item['subtotal']))
            
            c.execute('UPDATE produtos SET quantidade = quantidade - ? WHERE id = ?',
                      (item['quantidade'], item['produto_id']))
        
        # Criar dívida se necessário
        if data['tipo_pagamento'] == 'credito':
            c.execute('''INSERT INTO dividas (venda_id, cliente_nome, valor_total)
                         VALUES (?, ?, ?)''',
                      (venda_id, data['cliente_nome'], data['valor_total']))
        
        # Pagar dívida existente
        if data.get('divida_paga_id'):
            divida_id = data['divida_paga_id']
            c.execute('UPDATE dividas SET valor_pago = valor_pago + ? WHERE id = ?',
                      (data['valor_total'], divida_id))
            
            c.execute('SELECT valor_total, valor_pago FROM dividas WHERE id = ?', (divida_id,))
            divida = c.fetchone()
            if divida[1] >= divida[0]:
                c.execute('UPDATE dividas SET status = "pago" WHERE id = ?', (divida_id,))
        
        conn.commit()
        conn.close()
        return jsonify({
            'id': venda_id,
            'sessao_id': sessao_id,
            'message': 'Venda registrada com sucesso!'
        })
    
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f'Erro ao criar venda: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/vendas', methods=['GET'])
def get_vendas():
    vendedor_id = request.args.get('vendedor_id', type=int)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if vendedor_id:
        c.execute('''SELECT v.*, vd.nome as vendedor_nome 
                     FROM vendas v
                     JOIN vendedores vd ON v.vendedor_id = vd.id
                     WHERE v.cancelada = 0 AND v.vendedor_id = ?
                     ORDER BY v.data_venda DESC
                     LIMIT 50''', (vendedor_id,))
    else:
        c.execute('''SELECT v.*, vd.nome as vendedor_nome 
                     FROM vendas v
                     JOIN vendedores vd ON v.vendedor_id = vd.id
                     WHERE v.cancelada = 0
                     ORDER BY v.data_venda DESC
                     LIMIT 50''')
    
    vendas = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(vendas)

@app.route('/api/vendas/<int:id>/cancelar', methods=['POST'])
def cancelar_venda(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        c.execute('SELECT produto_id, quantidade FROM itens_venda WHERE venda_id = ?', (id,))
        itens = c.fetchall()
        
        for produto_id, quantidade in itens:
            c.execute('UPDATE produtos SET quantidade = quantidade + ? WHERE id = ?',
                      (quantidade, produto_id))
        
        c.execute('UPDATE vendas SET cancelada = 1 WHERE id = ?', (id,))
        c.execute('UPDATE dividas SET status = "cancelada" WHERE venda_id = ? AND status = "pendente"', (id,))
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Venda cancelada com sucesso! Produtos devolvidos ao estoque.'})
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/vendas/totais', methods=['GET'])
def get_totais_vendas():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT tipo_pagamento, SUM(valor_total) as total
                 FROM vendas
                 WHERE cancelada = 0
                 GROUP BY tipo_pagamento''')
    
    totais = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    return jsonify({
        'dinheiro': totais.get('dinheiro', 0),
        'banco': totais.get('banco', 0),
        'credito': totais.get('credito', 0)
    })

# ============= DÍVIDAS =============

@app.route('/api/dividas', methods=['GET'])
def get_dividas():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT d.*, v.vendedor_id, vd.nome as vendedor_nome
                 FROM dividas d
                 JOIN vendas v ON d.venda_id = v.id
                 JOIN vendedores vd ON v.vendedor_id = vd.id
                 WHERE d.status = 'pendente'
                 ORDER BY d.data_criacao DESC''')
    dividas = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(dividas)

# ============= RELATÓRIOS =============

@app.route('/api/relatorios/vendas', methods=['GET'])
def relatorio_vendas():
    """Relatório geral de vendas com filtros"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    vendedor_id = request.args.get('vendedor_id', type=int)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Construir query com filtros
    where_clauses = ['v.cancelada = 0']
    params = []
    
    if data_inicio and data_fim:
        where_clauses.append('DATE(v.data_venda) BETWEEN ? AND ?')
        params.extend([data_inicio, data_fim])
    
    if vendedor_id:
        where_clauses.append('v.vendedor_id = ?')
        params.append(vendedor_id)
    
    where_sql = ' AND '.join(where_clauses)
    
    # Vendas por tipo
    c.execute(f'''SELECT tipo_pagamento, COUNT(*) as total, SUM(valor_total) as valor
                  FROM vendas v
                  WHERE {where_sql}
                  GROUP BY tipo_pagamento''', params)
    vendas_tipo = [dict(row) for row in c.fetchall()]
    
    # Vendas por vendedor
    c.execute(f'''SELECT vd.nome, COUNT(*) as total, SUM(v.valor_total) as valor
                  FROM vendas v
                  JOIN vendedores vd ON v.vendedor_id = vd.id
                  WHERE {where_sql}
                  GROUP BY vd.nome''', params)
    vendas_vendedor = [dict(row) for row in c.fetchall()]
    
    # Dívidas pendentes
    c.execute('SELECT SUM(valor_total - valor_pago) FROM dividas WHERE status="pendente"')
    dividas_total = c.fetchone()[0] or 0
    
    conn.close()
    
    return jsonify({
        'vendas_por_tipo': vendas_tipo,
        'vendas_por_vendedor': vendas_vendedor,
        'dividas_pendentes': dividas_total
    })

@app.route('/api/relatorios/sessoes', methods=['GET'])
def relatorio_sessoes():
    """Relatório de sessões com filtros"""
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    vendedor_id = request.args.get('vendedor_id', type=int)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Construir query
    where_clauses = []
    params = []
    
    if data_inicio and data_fim:
        where_clauses.append('r.data_sessao BETWEEN ? AND ?')
        params.extend([data_inicio, data_fim])
    
    if vendedor_id:
        where_clauses.append('r.vendedor_id = ?')
        params.append(vendedor_id)
    
    where_sql = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''
    
    c.execute(f'''SELECT r.*, v.nome as vendedor_nome
                  FROM resumos_sessao r
                  JOIN vendedores v ON r.vendedor_id = v.id
                  {where_sql}
                  ORDER BY r.data_sessao DESC, r.hora_inicio DESC''', params)
    
    sessoes = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'sessoes': sessoes
    })

@app.route('/api/relatorios/diario', methods=['GET'])
def relatorio_diario():
    """Relatório diário agregado"""
    data = request.args.get('data', datetime.now().strftime('%Y-%m-%d'))
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Totais do dia
    c.execute('''SELECT 
                    COUNT(*) as total_vendas,
                    SUM(valor_total) as total_vendido,
                    SUM(CASE WHEN tipo_pagamento = 'dinheiro' THEN valor_total ELSE 0 END) as total_dinheiro,
                    SUM(CASE WHEN tipo_pagamento = 'banco' THEN valor_total ELSE 0 END) as total_banco,
                    SUM(CASE WHEN tipo_pagamento = 'credito' THEN valor_total ELSE 0 END) as total_credito
                 FROM vendas
                 WHERE DATE(data_venda) = ? AND cancelada = 0''', (data,))
    
    totais = dict(c.fetchone())
    
    # Resumos de sessões do dia
    c.execute('''SELECT r.*, v.nome as vendedor_nome
                 FROM resumos_sessao r
                 JOIN vendedores v ON r.vendedor_id = v.id
                 WHERE r.data_sessao = ?
                 ORDER BY r.hora_inicio''', (data,))
    
    sessoes = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'data': data,
        'totais': totais,
        'sessoes': sessoes
    })


# ============= INVENTÁRIO =============

@app.route('/api/inventario/iniciar', methods=['POST'])
def iniciar_inventario():
    """Inicia novo inventário buscando dados do último inventário finalizado"""
    try:
        data = request.json
        admin_usuario = str(data.get('admin_usuario', ''))
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Criar inventário
        agora = datetime.now()
        c.execute('''INSERT INTO inventarios 
                     (admin_usuario, status, data_inventario, hora_inventario, data_criacao)
                     VALUES (?, 'em_andamento', ?, ?, ?)''', 
                  (admin_usuario, agora.strftime('%Y-%m-%d'), 
                   agora.strftime('%H:%M:%S'), agora.strftime('%Y-%m-%d %H:%M:%S')))
        inventario_id = c.lastrowid
        
        # Buscar produtos
        c.execute('SELECT id, nome, quantidade, preco_venda, preco_compra FROM produtos ORDER BY nome')
        produtos = c.fetchall()
        
        # Buscar ÚLTIMO inventário finalizado
        c.execute('''SELECT MAX(id) FROM inventarios WHERE status = 'finalizado' ''')
        ultimo_inv_id = c.fetchone()[0]
        
        # Montar dicionário com quantidades do último inventário
        ultimo_inventario = {}
        if ultimo_inv_id:
            c.execute('''SELECT produto_id, quantidade_contada 
                         FROM itens_inventario 
                         WHERE inventario_id = ?''', (ultimo_inv_id,))
            for row in c.fetchall():
                ultimo_inventario[row[0]] = row[1]
        
        # Montar lista de produtos
        produtos_lista = []
        for p in produtos:
            produto_id = int(p[0])
            qtd_sistema_atual = int(p[2])
            qtd_ultimo_inv = ultimo_inventario.get(produto_id, qtd_sistema_atual)
            
            # Calcular vendas entre inventários
            vendas_calculadas = qtd_ultimo_inv - qtd_sistema_atual
            
            produtos_lista.append({
                'id': produto_id,
                'nome': str(p[1]),
                'quantidade_ultimo_inventario': qtd_ultimo_inv,
                'quantidade_sistema_atual': qtd_sistema_atual,
                'vendas_calculadas': vendas_calculadas,
                'quantidade_contada': 0,
                'preco_venda': float(p[3]),
                'preco_compra': float(p[4])
            })
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'inventario_id': inventario_id,
            'produtos': produtos_lista
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/inventario/salvar', methods=['POST'])
def salvar_inventario():
    """Salva contagem"""
    conn = None
    try:
        print("DEBUG: Salvando inventário...")
        data = request.json
        inventario_id = int(data.get('inventario_id'))
        itens = data.get('itens', [])
        
        print(f"DEBUG: ID={inventario_id}, Itens={len(itens)}")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('DELETE FROM itens_inventario WHERE inventario_id = ?', (inventario_id,))
        
        total_div = 0
        total_vendido = 0.0
        custo_produtos_vendidos = 0.0
        
        for idx, item in enumerate(itens):
            produto_id = int(item.get('id', 0))
            nome = str(item.get('nome', 'Sem nome'))
            qtd_ultimo_inv = int(item.get('quantidade_ultimo_inventario', 0))
            qtd_sistema = int(item.get('quantidade_sistema_atual', 0))
            vendas_calc = int(item.get('vendas_calculadas', 0))
            qtd_contada = int(item.get('quantidade_contada', 0))
            preco_venda = float(item.get('preco_venda', 0))
            preco_compra = float(item.get('preco_compra', preco_venda * 0.6))
            
            diferenca = qtd_ultimo_inv - qtd_contada
            divergencia_auditoria = vendas_calc - diferenca
            valor_diferenca = diferenca * preco_venda
            
            if diferenca != 0:
                total_div += 1
            
            if diferenca > 0:
                total_vendido += valor_diferenca
                custo_produtos_vendidos += diferenca * preco_compra
            
            c.execute('''INSERT INTO itens_inventario 
                         (inventario_id, produto_id, nome_produto, 
                          quantidade_inventario_anterior, quantidade_sistema,
                          quantidade_contada, vendas_calculadas,
                          diferenca, valor_diferenca, divergencia_auditoria)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (inventario_id, produto_id, nome, 
                       qtd_ultimo_inv, qtd_sistema, qtd_contada, vendas_calc,
                       diferenca, valor_diferenca, divergencia_auditoria))
        
        c.execute('''UPDATE inventarios 
                     SET total_produtos = ?, total_divergencias = ?, total_vendido_calculado = ?
                     WHERE id = ?''',
                  (len(itens), total_div, total_vendido, inventario_id))
        
        conn.commit()
        conn.close()
        
        print(f"DEBUG: Salvo! Total vendido: {total_vendido}")
        
        return jsonify({
            'success': True,
            'message': 'Inventário salvo',
            'total_divergencias': total_div,
            'total_vendido_calculado': float(total_vendido)
        })
        
    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except:
                pass
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/inventario/finalizar', methods=['POST'])
def finalizar_inventario():
    """Finaliza inventário"""
    try:
        data = request.json
        inventario_id = int(data.get('inventario_id'))
        obs = str(data.get('observacoes', ''))
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('SELECT * FROM inventarios WHERE id = ?', (inventario_id,))
        inv = c.fetchone()
        
        if not inv:
            conn.close()
            return jsonify({'success': False, 'message': 'Não encontrado'}), 404
        
        agora = datetime.now()
        c.execute('''UPDATE inventarios 
                     SET status = 'finalizado', observacoes = ?, data_finalizacao = ?
                     WHERE id = ?''',
                  (obs, agora.strftime('%Y-%m-%d %H:%M:%S'), inventario_id))
        
        c.execute('''SELECT 
                        COALESCE(SUM(CASE WHEN diferenca > 0 THEN diferenca ELSE 0 END), 0) as uv,
                        COALESCE(SUM(CASE WHEN diferenca > 0 THEN valor_diferenca ELSE 0 END), 0) as vv
                     FROM itens_inventario WHERE inventario_id = ?''', (inventario_id,))
        
        r = c.fetchone()
        resumo = {
            'unidades_vendidas': int(r['uv']),
            'valor_vendido': float(r['vv'])
        }
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'resumo': resumo})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/inventario/<int:id>', methods=['GET'])
def obter_inventario(id):
    """Detalhes do inventário"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('SELECT * FROM inventarios WHERE id = ?', (id,))
        inv = c.fetchone()
        
        if not inv:
            conn.close()
            return jsonify({'success': False}), 404
        
        c.execute('SELECT * FROM itens_inventario WHERE inventario_id = ?', (id,))
        itens = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({'success': True, 'inventario': dict(inv), 'itens': itens})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/inventario/historico', methods=['GET'])
def historico_inventarios():
    """Lista inventários"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('SELECT * FROM inventarios ORDER BY data_inventario DESC LIMIT 50')
        inventarios = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({'success': True, 'inventarios': inventarios})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500




# ============= GESTÃO DE TURNOS =============

@app.route('/api/gestao/turnos', methods=['GET'])
def listar_gestao_turnos():
    """Lista todos os turnos da gestão"""
    try:
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        if data_inicio and data_fim:
            c.execute('''SELECT * FROM gestao_turnos 
                         WHERE data BETWEEN ? AND ?
                         ORDER BY data DESC, hora_abertura DESC''',
                      (data_inicio, data_fim))
        else:
            c.execute('''SELECT * FROM gestao_turnos 
                         ORDER BY data DESC, hora_abertura DESC 
                         LIMIT 100''')
        
        turnos = [dict(row) for row in c.fetchall()]
        conn.close()
        
        return jsonify({'success': True, 'turnos': turnos})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/gestao/resumo', methods=['GET'])
def resumo_gestao():
    """Resumo geral da gestão"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Totais gerais
        c.execute('''SELECT 
                        COUNT(*) as total_turnos,
                        SUM(quantidade_vendas) as total_vendas,
                        SUM(total_vendido_cash) as total_cash,
                        SUM(total_vendido_banco) as total_banco,
                        SUM(total_dividas) as total_dividas,
                        SUM(global_vendido) as global_vendido
                     FROM gestao_turnos''')
        
        totais = dict(c.fetchone())
        
        # Por vendedor
        c.execute('''SELECT 
                        vendedor_nome,
                        COUNT(*) as turnos,
                        SUM(quantidade_vendas) as vendas,
                        SUM(global_vendido) as total
                     FROM gestao_turnos
                     GROUP BY vendedor_id, vendedor_nome
                     ORDER BY total DESC''')
        
        por_vendedor = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'totais': totais,
            'por_vendedor': por_vendedor
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500





@app.route('/api/dividas/pagar', methods=['POST'])
def pagar_divida():
    """Registra pagamento de dívida sem adicionar ao carrinho"""
    data = request.json
    divida_id = data.get('divida_id')
    valor_pago = float(data.get('valor_pago', 0))
    tipo_pagamento = data.get('tipo_pagamento', 'dinheiro')
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Buscar dívida
        c.execute('SELECT * FROM dividas WHERE id = ?', (divida_id,))
        divida = c.fetchone()
        
        if not divida:
            conn.close()
            return jsonify({'success': False, 'message': 'Dívida não encontrada'}), 404
        
        venda_id = divida['venda_id']
        valor_total = divida['valor_total']
        valor_ja_pago = divida['valor_pago']
        valor_restante = valor_total - valor_ja_pago
        
        # Validar valor
        if valor_pago <= 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Valor inválido'}), 400
        
        if valor_pago > valor_restante:
            conn.close()
            return jsonify({'success': False, 'message': f'Valor maior que o restante (Kz {valor_restante:.2f})'}), 400
        
        # Atualizar dívida
        novo_valor_pago = valor_ja_pago + valor_pago
        novo_status = 'paga' if novo_valor_pago >= valor_total else 'pendente'
        
        # Se foi totalmente paga, registrar data de pagamento
        from datetime import datetime
        if novo_status == 'paga':
            data_pagamento = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''UPDATE dividas 
                         SET valor_pago = ?, status = ?, data_pagamento = ?
                         WHERE id = ?''',
                      (novo_valor_pago, novo_status, data_pagamento, divida_id))
        else:
            c.execute('''UPDATE dividas 
                         SET valor_pago = ?, status = ?
                         WHERE id = ?''',
                      (novo_valor_pago, novo_status, divida_id))
        
        # SE DÍVIDA FOI TOTALMENTE PAGA, APAGAR A VENDA DE CRÉDITO
        if novo_status == 'paga':
            print(f"DEBUG: Dívida {divida_id} totalmente paga. Apagando venda {venda_id}...")
            
            # Apagar itens da venda
            c.execute('DELETE FROM itens_venda WHERE venda_id = ?', (venda_id,))
            
            # Apagar a venda
            c.execute('DELETE FROM vendas WHERE id = ?', (venda_id,))
            
            print(f"DEBUG: Venda {venda_id} apagada do histórico.")
        
        conn.commit()
        conn.close()
        
        logger.info(f'Pagamento de dívida ID {divida_id}: Kz {valor_pago:.2f} ({tipo_pagamento}). Status: {novo_status}')
        
        return jsonify({
            'success': True,
            'message': f'Pagamento de Kz {valor_pago:.2f} registrado com sucesso!' + 
                      (' Venda removida do histórico.' if novo_status == 'paga' else ''),
            'novo_status': novo_status,
            'valor_restante': float(valor_total - novo_valor_pago)
        })
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f'Erro ao pagar dívida: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/inventario/<int:id>', methods=['DELETE'])
def apagar_inventario(id):
    """Apaga um inventário finalizado"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Verificar se inventário existe
        c.execute('SELECT status FROM inventarios WHERE id = ?', (id,))
        inv = c.fetchone()
        
        if not inv:
            conn.close()
            return jsonify({'success': False, 'message': 'Inventário não encontrado'}), 404
        
        # Apagar itens do inventário
        c.execute('DELETE FROM itens_inventario WHERE inventario_id = ?', (id,))
        
        # Apagar inventário
        c.execute('DELETE FROM inventarios WHERE id = ?', (id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Inventário apagado com sucesso'})
        
    except Exception as e:
        print(f"ERRO ao apagar inventário: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
