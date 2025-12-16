import os
import re
from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'elite_poker_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lucky_poker_elite.db'
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(20), unique=True)
    country_code = db.Column(db.String(10))
    password = db.Column(db.String(100))
    balance = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Subscription Logic
    sub_expiry = db.Column(db.DateTime, nullable=True) # When their 24h ends

    @property
    def has_active_sub(self):
        if self.is_admin: return True # Admin is always active
        if not self.sub_expiry: return False
        return self.sub_expiry > datetime.now()

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stake = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    creator_choice = db.Column(db.String(10)) # 'Red' or 'Black'
    hint = db.Column(db.String(100)) # Mind games
    status = db.Column(db.String(20), default='OPEN') 
    
    challenger_id = db.Column(db.Integer)
    winner_id = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.now)

class AdminVault(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commission_balance = db.Column(db.Integer, default=0) # 10% from games
    sub_balance = db.Column(db.Integer, default=0) # 1k from daily fees

# --- STYLES ---
common_style = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Roboto:wght@300;400;700&display=swap');

    :root { --bg: #0b0f19; --card: #151a28; --gold: #ffd700; --text: #e2e8f0; --red: #ef4444; --green: #10b981; --accent: #3b82f6; }
    
    body { font-family: 'Roboto', sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding-bottom: 90px; }
    
    /* Header */
    .header { background: rgba(21, 26, 40, 0.95); padding: 15px 20px; border-bottom: 1px solid #333; position: sticky; top: 0; z-index: 100; display: flex; justify-content: space-between; align-items: center; }
    .logo { font-family: 'Orbitron', sans-serif; font-size: 18px; font-weight: 900; color: var(--gold); letter-spacing: 2px; }
    
    .money-pill { background: rgba(16, 185, 129, 0.1); border: 1px solid var(--green); padding: 5px 12px; border-radius: 20px; font-weight: bold; color: var(--green); font-size: 14px; }

    /* Instructions Modal */
    .info-box { background: rgba(59, 130, 246, 0.1); border-left: 4px solid var(--accent); padding: 15px; margin: 20px; border-radius: 8px; font-size: 13px; line-height: 1.5; }

    /* Cards */
    .game-card { background: var(--card); margin: 15px 20px; padding: 20px; border-radius: 16px; border: 1px solid #333; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 20px rgba(0,0,0,0.3); position: relative; overflow: hidden; }
    .game-card::before { content:''; position: absolute; top:0; left:0; width: 4px; height: 100%; background: var(--gold); }
    
    .stake-lbl { font-size: 10px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
    .stake-val { font-size: 22px; font-weight: 900; color: #fff; font-family: 'Orbitron'; }
    .hint-text { font-size: 12px; color: var(--accent); font-style: italic; margin-top: 5px; }

    .btn-play { background: var(--gold); color: black; border: none; padding: 10px 25px; border-radius: 30px; font-weight: 900; cursor: pointer; box-shadow: 0 0 15px rgba(255, 215, 0, 0.2); }

    /* Form Elements */
    .input-group { margin-bottom: 15px; text-align: left; }
    label { font-size: 11px; font-weight: bold; color: #888; text-transform: uppercase; margin-bottom: 5px; display: block; }
    input, select { width: 100%; padding: 15px; background: #1f2536; border: 1px solid #333; color: white; border-radius: 10px; box-sizing: border-box; font-size: 16px; }
    input:focus { outline: none; border-color: var(--gold); }

    .btn-main { width: 100%; padding: 15px; background: var(--gold); color: black; border: none; border-radius: 10px; font-weight: bold; font-size: 16px; cursor: pointer; text-transform: uppercase; }
    .btn-red { background: var(--red); color: white; }
    .btn-black { background: #222; border: 1px solid #555; color: white; }

    /* Paywall */
    .paywall { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 200; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 20px; box-sizing: border-box; }
    .lock-icon { font-size: 60px; margin-bottom: 20px; }

    /* Admin Panel */
    .admin-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 20px; }
    .stat-box { background: var(--card); padding: 15px; border-radius: 10px; text-align: center; border: 1px solid #333; }
    .stat-num { font-size: 20px; font-weight: bold; color: var(--gold); }

    /* Tabs */
    .tabs { display: flex; overflow-x: auto; gap: 10px; padding: 10px 20px; border-bottom: 1px solid #222; }
    .tab { background: #1f2536; padding: 8px 16px; border-radius: 20px; color: #888; text-decoration: none; font-size: 12px; font-weight: bold; white-space: nowrap; border: 1px solid transparent; }
    .tab.active { background: var(--gold); color: black; }

    .nav { position: fixed; bottom: 0; width: 100%; background: #151a28; padding: 12px 0; border-top: 1px solid #333; display: flex; justify-content: space-around; z-index: 90; }
    .nav a { color: #666; text-decoration: none; font-size: 22px; }
    .nav a.active { color: var(--gold); }
    
    .fab { position: fixed; bottom: 80px; right: 20px; width: 60px; height: 60px; background: var(--gold); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 30px; color: black; text-decoration: none; box-shadow: 0 10px 30px rgba(0,0,0,0.5); z-index: 80; font-weight: bold; }
    
    /* Alerts */
    .alert { background: rgba(239, 68, 68, 0.2); color: #fca5a5; padding: 15px; margin: 20px; border-radius: 8px; font-size: 13px; text-align: center; border: 1px solid var(--red); }
</style>
"""

# --- TEMPLATES ---

dashboard_html = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body>
    <div class="header">
        <div>
            <div class="logo">LUCKY POKER</div>
            <div style="font-size:10px; color:#888;">{{ current_user.username }}</div>
        </div>
        <div class="money-pill">{{ current_user.balance | money }}</div>
    </div>

    <div class="info-box">
        <b>HOW IT WORKS:</b><br>
        1. Pay 1k Daily Access Fee.<br>
        2. Set a card (Red/Black) or Challenge others.<br>
        3. Match the color to win the pot!<br>
        <span style="color:var(--accent);">Admin Fee: 10% on wins.</span>
    </div>

    <div class="tabs">
        <a href="/?tier=1k" class="tab {{ 'active' if tier == '1k' else '' }}">1K STAKE</a>
        <a href="/?tier=2k" class="tab {{ 'active' if tier == '2k' else '' }}">2K STAKE</a>
        <a href="/?tier=5k" class="tab {{ 'active' if tier == '5k' else '' }}">5K STAKE</a>
        <a href="/?tier=10k" class="tab {{ 'active' if tier == '10k' else '' }}">10K STAKE</a>
        <a href="/?tier=20k" class="tab {{ 'active' if tier == '20k' else '' }}">20K STAKE</a>
        <a href="/?tier=50k" class="tab {{ 'active' if tier == '50k' else '' }}">50K STAKE</a>
    </div>

    <div style="padding-bottom:20px;">
        {% for game in games %}
        <div class="game-card">
            <div>
                <div class="stake-lbl">POT VALUE</div>
                <div class="stake-val">{{ (game.stake * 2) | money }}</div>
                <div class="hint-text">"{{ game.hint }}"</div>
                <div style="font-size:10px; color:#666; margin-top:5px;">Set by: {{ users.get(game.creator_id).username }}</div>
            </div>
            
            {% if game.creator_id == current_user.id %}
                <button style="background:#333; color:#555; padding:10px 20px; border:none; border-radius:20px; font-size:12px;">WAITING</button>
            {% else %}
                <a href="/play/{{ game.id }}" class="btn-play">PLAY</a>
            {% endif %}
        </div>
        {% else %}
        <div style="text-align:center; padding:40px; color:#666;">
            No games in {{ tier }} category.<br>Create one!
        </div>
        {% endfor %}
    </div>

    <a href="/create_game" class="fab">+</a>

    <div class="nav">
        <a href="/" class="active">🏠</a>
        <a href="/wallet">💳</a>
        {% if current_user.is_admin %}
        <a href="/admin" style="color:var(--red);">👑</a>
        {% endif %}
        <a href="/logout">🚪</a>
    </div>
</body></html>
"""

paywall_html = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body>
    <div class="paywall">
        <div class="lock-icon">🔒</div>
        <h2 style="color:var(--gold);">DAILY ACCESS EXPIRED</h2>
        <p style="color:#aaa; margin-bottom:30px;">
            To maintain high quality games, we charge a small daily fee of <b>1,000 UGX</b> for 24-hour access.
        </p>
        
        <div style="background:#151a28; padding:20px; border-radius:15px; width:100%; margin-bottom:20px;">
            <div style="font-size:12px; color:#888;">YOUR BALANCE</div>
            <div style="font-size:24px; font-weight:bold; color:var(--green);">{{ current_user.balance | money }}</div>
        </div>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="alert">{{ messages[0] }}</div>
        {% endif %}
        {% endwith %}

        <form method="POST" action="/pay_sub" style="width:100%;">
            <button class="btn-main">PAY 1K & UNLOCK</button>
        </form>
        
        <br>
        <a href="/wallet" style="color:var(--accent); font-size:12px;">Deposit Funds First?</a>
        <br><br>
        <a href="/logout" style="color:#666; font-size:12px;">Logout</a>
    </div>
</body></html>
"""

create_game_html = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body>
    <div class="header"><div class="logo">NEW GAME</div><a href="/" style="color:#fff; text-decoration:none;">✕</a></div>
    
    <div class="container">
        <div style="background:var(--card); padding:20px; border-radius:15px;">
            <form method="POST">
                <div class="input-group">
                    <label>SELECT STAKE CATEGORY</label>
                    <select name="stake">
                        <option value="1000">1,000 UGX</option>
                        <option value="2000">2,000 UGX</option>
                        <option value="5000">5,000 UGX</option>
                        <option value="10000">10,000 UGX</option>
                        <option value="20000">20,000 UGX</option>
                        <option value="50000">50,000 UGX</option>
                    </select>
                </div>

                <div class="input-group">
                    <label>SELECT HINT (MIND GAMES)</label>
                    <select name="hint">
                        <option>Trust your gut</option>
                        <option>I love the color of blood</option>
                        <option>Darkness is my friend</option>
                        <option>It's definitely Red</option>
                        <option>It's definitely Black</option>
                        <option>Pure Luck</option>
                        <option>Don't overthink it</option>
                    </select>
                </div>

                <div class="input-group">
                    <label>HIDE YOUR CARD</label>
                    <div style="display:flex; gap:10px;">
                        <button type="submit" name="choice" value="Red" class="btn-main btn-red">🟥 RED</button>
                        <button type="submit" name="choice" value="Black" class="btn-main btn-black">⬛ BLACK</button>
                    </div>
                </div>
            </form>
        </div>
    </div>
</body></html>
"""

play_html = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body>
    <div class="header"><div class="logo">CHALLENGE</div><a href="/" style="color:#fff; text-decoration:none;">✕</a></div>
    
    <div class="container" style="text-align:center;">
        <div style="margin-top:20px; margin-bottom:40px;">
            <div style="font-size:12px; color:#888;">POT TO WIN</div>
            <div style="font-size:40px; font-weight:900; color:var(--gold);">{{ (game.stake * 2 * 0.9) | money }}</div>
            <div style="font-size:10px; color:#666;">(After 10% Fee)</div>
        </div>

        <div style="background:#222; padding:15px; border-radius:10px; display:inline-block; margin-bottom:30px; border:1px solid #444;">
            <div style="font-size:10px; color:var(--accent); font-weight:bold;">CREATOR HINT:</div>
            <div style="font-style:italic; font-size:14px; margin-top:5px;">"{{ game.hint }}"</div>
        </div>

        <form method="POST" action="/resolve_game/{{ game.id }}">
            <p style="color:#aaa; font-size:12px; margin-bottom:15px;">MATCH THE HIDDEN CARD:</p>
            <div style="display:flex; gap:15px;">
                <button name="guess" value="Red" class="btn-main btn-red">IT'S RED</button>
                <button name="guess" value="Black" class="btn-main btn-black">IT'S BLACK</button>
            </div>
        </form>
    </div>
</body></html>
"""

wallet_html = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body>
    <div class="header"><div class="logo">WALLET</div></div>
    
    <div class="container">
        <div style="text-align:center; padding:30px 0;">
            <div style="font-size:12px; color:#888;">AVAILABLE FUNDS</div>
            <div style="font-size:35px; font-weight:bold; color:var(--green);">{{ current_user.balance | money }}</div>
        </div>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="alert">{{ messages[0] }}</div>
        {% endif %}
        {% endwith %}

        <div style="background:var(--card); padding:20px; border-radius:15px;">
            <form method="POST" action="/transact">
                <label>TRANSACTION TYPE</label>
                <select name="type">
                    <option value="deposit">📥 Deposit (Add Money)</option>
                    <option value="withdraw">📤 Withdraw (Cash Out)</option>
                </select>
                
                <label>AMOUNT</label>
                <input type="number" name="amount" placeholder="e.g. 10000" required>
                
                <button class="btn-main">PROCESS</button>
            </form>
        </div>
    </div>
    
    <div class="nav">
        <a href="/">🏠</a>
        <a href="/wallet" class="active">💳</a>
        {% if current_user.is_admin %}<a href="/admin">👑</a>{% endif %}
        <a href="/logout">🚪</a>
    </div>
</body></html>
"""

admin_html = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body>
    <div class="header"><div class="logo">ADMIN VAULT</div><a href="/" style="color:#fff; text-decoration:none;">✕</a></div>
    
    <div class="container">
        <div class="admin-stats">
            <div class="stat-box">
                <div class="stake-lbl">GAME FEES (10%)</div>
                <div class="stat-num">{{ vault.commission_balance | money }}</div>
            </div>
            <div class="stat-box">
                <div class="stake-lbl">SUB FEES (100%)</div>
                <div class="stat-num">{{ vault.sub_balance | money }}</div>
            </div>
        </div>

        <div style="background:var(--card); padding:20px; border-radius:15px; margin-top:20px;">
            <h3 style="color:var(--gold);">Withdraw Profits</h3>
            <p style="font-size:12px; color:#aaa;">Transfer system earnings to your personal account.</p>
            <form method="POST" action="/admin_withdraw">
                <button class="btn-main">WITHDRAW ALL TO MY BALANCE</button>
            </form>
        </div>

        <div style="margin-top:30px;">
            <h4 style="color:#888;">ALL USERS ({{ users|length }})</h4>
            {% for u in users %}
            <div style="padding:10px; border-bottom:1px solid #333; display:flex; justify-content:space-between; font-size:12px;">
                <span>{{ u.username }}</span>
                <span style="color:var(--green);">{{ u.balance | money }}</span>
            </div>
            {% endfor %}
        </div>
    </div>
</body></html>
"""

auth_html = """
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">""" + common_style + """</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh;">
    <div style="width:85%; max-width:350px;">
        <div style="text-align:center; margin-bottom:30px;">
            <div class="logo" style="font-size:30px;">LUCKY POKER</div>
            <div style="color:var(--gold); font-size:12px; letter-spacing:2px;">ELITE EDITION</div>
        </div>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="alert">{{ messages[0] }}</div>
        {% endif %}
        {% endwith %}

        <div style="background:var(--card); padding:25px; border-radius:20px; border:1px solid #333;">
            <h3 style="text-align:center; margin-top:0;">{{ title }}</h3>
            <form method="POST">
                {% if mode == 'register' %}
                <div style="display:flex; gap:10px; margin-bottom:10px;">
                    <select name="country_code" style="width:35%; margin:0;"><option>+256</option><option>+254</option></select>
                    <input type="tel" name="phone" placeholder="Phone" style="margin:0;" required>
                </div>
                <input type="text" name="username" placeholder="Username" required>
                
                <input type="password" name="password" placeholder="Password (Capital & Special Char)" required>
                
                <input type="text" name="admin_code" placeholder="Admin Code (Optional)">
                {% endif %}
                
                {% if mode == 'login' %}
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                {% endif %}
                
                <button class="btn-main" style="margin-top:15px;">{{ btn_text }}</button>
            </form>
            <p style="text-align:center; font-size:12px; margin-top:20px;">
                <a href="{{ link_url }}" style="color:#aaa;">{{ link_text }}</a>
            </p>
        </div>
    </div>
</body></html>
"""

# --- FILTERS ---
@app.template_filter()
def money(value):
    if value >= 1000000:
        return f"{value/1000000:.1f}M"
    if value >= 1000:
        return f"{value/1000:.1f}K"
    return f"{value}"

# --- ROUTES ---

@app.route('/')
@login_required
def home():
    # 1. SUBSCRIPTION CHECK
    if not current_user.has_active_sub:
        return render_template_string(paywall_html)

    # 2. LOAD GAMES BY TIER
    tier = request.args.get('tier', '1k')
    stake_val = 1000
    if tier == '2k': stake_val = 2000
    elif tier == '5k': stake_val = 5000
    elif tier == '10k': stake_val = 10000
    elif tier == '20k': stake_val = 20000
    elif tier == '50k': stake_val = 50000
    
    games = Game.query.filter_by(status='OPEN', stake=stake_val).all()
    users = {u.id: u for u in User.query.all()} # For names
    
    return render_template_string(dashboard_html, games=games, tier=tier, users=users)

@app.route('/pay_sub', methods=['POST'])
@login_required
def pay_sub():
    if current_user.balance < 1000:
        flash("Insufficient Funds. Please Deposit.")
        return redirect(url_for('wallet')) # Should redirect to wallet, but reusing paywall for now
    
    current_user.balance -= 1000
    current_user.sub_expiry = datetime.now() + timedelta(hours=24)
    
    # Add to Vault
    vault = AdminVault.query.first()
    if not vault: vault = AdminVault()
    vault.sub_balance += 1000
    db.session.add(vault)
    
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/create_game', methods=['GET', 'POST'])
@login_required
def create_game():
    if not current_user.has_active_sub: return redirect(url_for('home'))
    
    if request.method == 'POST':
        stake = int(request.form.get('stake'))
        choice = request.form.get('choice')
        hint = request.form.get('hint')
        
        if current_user.balance < stake:
            flash("Insufficient Balance")
            return redirect(url_for('wallet'))
            
        current_user.balance -= stake
        new_game = Game(stake=stake, creator_id=current_user.id, creator_choice=choice, hint=hint)
        db.session.add(new_game)
        db.session.commit()
        return redirect(url_for('home'))
        
    return render_template_string(create_game_html)

@app.route('/play/<int:id>')
@login_required
def play(id):
    if not current_user.has_active_sub: return redirect(url_for('home'))
    game = Game.query.get(id)
    if game.creator_id == current_user.id: return "Cannot play own game"
    if game.status != 'OPEN': return "Game closed"
    return render_template_string(play_html, game=game)

@app.route('/resolve_game/<int:id>', methods=['POST'])
@login_required
def resolve_game(id):
    game = Game.query.get(id)
    guess = request.form.get('guess')
    
    if current_user.balance < game.stake:
        flash("Insufficient Funds")
        return redirect(url_for('wallet'))
    
    current_user.balance -= game.stake
    
    # Logic: Match = Challenger Wins. Mismatch = Creator Wins.
    winner_id = current_user.id if guess == game.creator_choice else game.creator_id
    
    # Payout
    total_pot = game.stake * 2
    commission = int(total_pot * 0.10) # 10%
    payout = total_pot - commission
    
    winner = User.query.get(winner_id)
    winner.balance += payout
    
    # Admin Vault Update
    vault = AdminVault.query.first()
    if not vault: vault = AdminVault()
    vault.commission_balance += commission
    db.session.add(vault)
    
    game.status = 'CLOSED'
    game.winner_id = winner_id
    game.challenger_id = current_user.id
    db.session.commit()
    
    return redirect(url_for('home'))

@app.route('/wallet', methods=['GET'])
@login_required
def wallet():
    return render_template_string(wallet_html)

@app.route('/transact', methods=['POST'])
@login_required
def transact():
    t_type = request.form.get('type')
    amount = int(request.form.get('amount'))
    
    if t_type == 'deposit':
        current_user.balance += amount
    elif t_type == 'withdraw':
        if current_user.balance >= amount:
            current_user.balance -= amount
        else:
            flash("Low Balance")
            return redirect(url_for('wallet'))
            
    db.session.add(Transaction(user_id=current_user.id, type=t_type, amount=amount))
    db.session.commit()
    return redirect(url_for('wallet'))

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin: return "Access Denied"
    vault = AdminVault.query.first()
    users = User.query.all()
    return render_template_string(admin_html, vault=vault, users=users)

@app.route('/admin_withdraw', methods=['POST'])
@login_required
def admin_withdraw():
    if not current_user.is_admin: return "Access Denied"
    vault = AdminVault.query.first()
    
    total = vault.commission_balance + vault.sub_balance
    current_user.balance += total
    
    vault.commission_balance = 0
    vault.sub_balance = 0
    db.session.commit()
    return redirect(url_for('wallet'))

# --- AUTH ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('home'))
        flash("Invalid Login")
    return render_template_string(auth_html, mode='login', title='LOGIN', btn_text='ENTER', link_text='New? Create Account', link_url='/register')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form.get('username')
        pwd = request.form.get('password')
        
        # Regex for Password: 1 Cap, 1 Special
        if not re.search(r"[A-Z]", pwd) or not re.search(r"[!@#$%^&*]", pwd):
            flash("Weak Password! Use 1 Capital & 1 Special Char.")
            return render_template_string(auth_html, mode='register', title='JOIN US', btn_text='REGISTER', link_text='Login', link_url='/login')
            
        if User.query.filter_by(username=uname).first():
            flash("Username taken")
            return render_template_string(auth_html, mode='register', title='JOIN US', btn_text='REGISTER', link_text='Login', link_url='/login')
            
        is_admin = request.form.get('admin_code') == 'BOSS2025'
        
        new_user = User(
            username=uname, 
            phone=request.form.get('phone'),
            country_code=request.form.get('country_code'),
            password=generate_password_hash(pwd, method='scrypt'),
            balance=5000, # Welcome bonus
            is_admin=is_admin
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
        
    return render_template_string(auth_html, mode='register', title='JOIN US', btn_text='REGISTER', link_text='Login', link_url='/login')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not AdminVault.query.first():
            db.session.add(AdminVault())
            db.session.commit()
    app.run(host='0.0.0.0', port=8080)