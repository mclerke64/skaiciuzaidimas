from flask import Flask, render_template, request, redirect, url_for, session
import time
import uuid
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SESSION_TYPE'] = 'filesystem'
from flask_session import Session
Session(app)

# Global variables to store game state
players = []
game_started = False
winners = []
countdown_start_time = None
countdown_duration = 3  # 3-second countdown
countdown_active = False
game_id = str(uuid.uuid4())
last_activity_time = time.time()

def get_middle_players(players):
    print(f"Calculating middle players for: {players}")
    if len(players) < 3:
        return []
    guess_counts = {}
    for p in players:
        guess_counts[p['guess']] = guess_counts.get(p['guess'], 0) + 1
    unique_guesses = sorted(guess_counts.keys())
    print(f"Unique guesses with counts: {guess_counts}")
    if len(unique_guesses) < 3:
        return []
    if len(unique_guesses) % 2 == 0:
        return []
    middle_index = len(unique_guesses) // 2
    middle_guess = unique_guesses[middle_index]
    print(f"Middle guess: {middle_guess}")
    middle_players = [p for p in players if p['guess'] == middle_guess and guess_counts[middle_guess] == 1]
    return middle_players if middle_players else []

@app.route('/', methods=['GET', 'POST'])
def index():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    try:
        if 'game_id' not in session or session.get('game_id') != game_id:
            session['game_id'] = game_id
            session['submitted'] = False
            print(f"New session initialized with game_id: {game_id}")
        
        if request.method == 'POST' and not game_started:
            name = request.form.get('name')
            guess = request.form.get('guess')
            if not name or not guess:
                return render_template('index.html', players=players, game_started=game_started,
                                      winners=winners, countdown_active=countdown_active,
                                      error="Please provide both name and guess!")
            try:
                guess = int(guess)
                if not (1 <= guess <= 100):
                    return render_template('index.html', players=players, game_started=game_started,
                                          winners=winners, countdown_active=countdown_active,
                                          error="Guess must be between 1 and 100!")
                if any(player['name'] == name for player in players):
                    return render_template('index.html', players=players, game_started=game_started,
                                          winners=winners, countdown_active=countdown_active,
                                          error="Name already taken!")
                players.append({'name': name, 'guess': guess})
                session['submitted'] = True
                print(f"Player added: {name}, guess: {guess}, total players: {len(players)}")
                last_activity_time = time.time()
                if len(players) >= 3 and not countdown_active:
                    countdown_active = True
                    countdown_start_time = time.time()
            except ValueError as ve:
                return render_template('index.html', players=players, game_started=game_started,
                                      winners=winners, countdown_active=countdown_active,
                                      error="Guess must be a valid number!")
            except Exception as e:
                print(f"Error adding player: {str(e)}")
                return render_template('index.html', players=players, game_started=game_started,
                                      winners=winners, countdown_active=countdown_active,
                                      error="An internal error occurred while adding player.")
        
        # Check if game should end and redirect
        if countdown_active:
            remaining_time = max(0, countdown_duration - (time.time() - countdown_start_time))
            if remaining_time <= 0:
                countdown_active = False
                game_started = True
                winners = get_middle_players(players)
                return redirect(url_for('result'))
        else:
            remaining_time = 0
        
        initial_players = [{'name': p['name'], 'guess': p['guess'] if game_started else 'hidden'} for p in players]
        return render_template('index.html', players=initial_players, game_started=game_started,
                              winners=winners, countdown_active=countdown_active,
                              remaining_time=remaining_time)
    except Exception as e:
        print(f"Unexpected error in index: {str(e)}")
        return render_template('index.html', players=players, game_started=game_started,
                              winners=winners, countdown_active=countdown_active,
                              error="An internal error occurred. Please try again.")

@app.route('/reset', methods=['POST'])
def reset():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    try:
        print('Resetting game')
        players = []
        game_started = False
        winners = []
        countdown_start_time = None
        countdown_active = False
        game_id = str(uuid.uuid4())
        session.clear()
        session['game_id'] = game_id
        session['submitted'] = False
        last_activity_time = time.time()
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error in reset: {str(e)}")
        return "Internal Server Error", 500

@app.route('/result')
def result():
    global players, game_started, winners, countdown_active
    if game_started:
        return render_template('result.html', players=players, winners=winners)
    return redirect(url_for('index'))

def auto_reset():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    while True:
        inactive_time = time.time() - last_activity_time
        if not countdown_active and not game_started and len(players) < 3 and inactive_time >= 10:
            print('Auto-resetting due to inactivity')
            players = []
            game_started = False
            winners = []
            countdown_start_time = None
            countdown_active = False
            game_id = str(uuid.uuid4())
        time.sleep(1)

if __name__ == '__main__':
    import threading
    threading.Thread(target=auto_reset, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
