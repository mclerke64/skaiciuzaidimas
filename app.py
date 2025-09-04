from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
import time
import uuid
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SESSION_TYPE'] = 'filesystem'  # Note: Switch to 'redis' with external Redis if possible
socketio = SocketIO(app, async_mode='threading', ping_timeout=60, ping_interval=25, logger=True, engineio_logger=True)
from flask_session import Session
Session(app)

# Global variables to store game state
players = []
game_started = False
winners = []
countdown_start_time = None
countdown_duration = 10
countdown_active = False
game_id = str(uuid.uuid4())
last_activity_time = time.time()
ROOM = 'game_room'

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

def broadcast_game_state():
    global last_activity_time
    last_activity_time = time.time()
    print(f"Broadcasting game state: players={len(players)}, game_started={game_started}, winners={winners}")
    try:
        socketio.emit('update_game_state', {
            'players': [{'name': p['name'], 'guess': p['guess'] if game_started else 'hidden'} for p in players],
            'game_started': game_started,
            'winners': winners
        }, room=ROOM, namespace='/', skip_sid=None)
    except Exception as e:
        print(f"Broadcast error: {str(e)}")

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
                broadcast_game_state()
                if len(players) >= 3 and not countdown_active:
                    countdown_active = True
                    countdown_start_time = time.time()
                    socketio.start_background_task(countdown)
                elif len(players) > 3 and countdown_active:
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
        initial_players = [{'name': p['name'], 'guess': p['guess'] if game_started else 'hidden'} for p in players]
        return render_template('index.html', players=initial_players, game_started=game_started,
                              winners=winners, countdown_active=countdown_active)
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
        socketio.emit('game_reset', {}, room=ROOM, namespace='/')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error in reset: {str(e)}")
        return "Internal Server Error", 500

def countdown():
    global countdown_active, game_started, winners, countdown_start_time, last_activity_time
    while countdown_active and countdown_start_time is not None:
        try:
            elapsed_time = time.time() - countdown_start_time
            remaining_time = max(0, countdown_duration - elapsed_time)
            socketio.emit('update_countdown', {
                'countdown_active': countdown_active,
                'remaining_time': remaining_time
            }, room=ROOM, namespace='/')
            print(f"Countdown: {remaining_time:.1f}s remaining")
            if remaining_time <= 0:
                countdown_active = False
                game_started = True
                winners = get_middle_players(players)
                broadcast_game_state()
                # Force server-side state update to ensure all see the result
                socketio.emit('force_update', {}, room=ROOM, namespace='/')
                break
            socketio.sleep(0.1)
        except Exception as e:
            print(f"Countdown error: {str(e)}")
            break

def auto_reset():
    global players, game_started, winners, countdown_start_time, countdown_active, game_id, last_activity_time
    while True:
        inactive_time = time.time() - last_activity_time
        # Only reset if game hasn't started and fewer than 3 players
        if not countdown_active and not game_started and len(players) < 3 and inactive_time >= 10:
            print('Auto-resetting due to inactivity')
            players = []
            game_started = False
            winners = []
            countdown_start_time = None
            countdown_active = False
            game_id = str(uuid.uuid4())
            socketio.emit('game_reset', {}, room=ROOM, namespace='/')
            broadcast_game_state()
            break
        socketio.sleep(1)

@socketio.on('connect', namespace='/')
def handle_connect():
    print('Client connected with sid:', request.sid)
    try:
        session['game_id'] = game_id  # Force a new session on connect
        session['submitted'] = False
        join_room(ROOM)
        # Send state to the connecting client
        emit('update_game_state', {
            'players': [{'name': p['name'], 'guess': p['guess'] if game_started else 'hidden'} for p in players],
            'game_started': game_started,
            'winners': winners
        }, room=request.sid, namespace='/')
        if countdown_active and countdown_start_time is not None:
            remaining_time = max(0, countdown_duration - (time.time() - countdown_start_time))
            emit('update_countdown', {
                'countdown_active': countdown_active,
                'remaining_time': remaining_time
            }, room=request.sid, namespace='/')
    except Exception as e:
        print(f"Error in connect: {str(e)}")

@socketio.on('disconnect', namespace='/')
def handle_disconnect():
    print(f'Client disconnected with session {request.sid}')
    try:
        if 'game_id' in session and session.get('game_id') == game_id:
            del session['game_id']
            del session['submitted']
    except Exception as e:
        print(f"Error in disconnect: {str(e)}")

@socketio.on('game_reset')
def handle_game_reset():
    try:
        session.clear()
        session['game_id'] = request.sid
        session['submitted'] = False
    except Exception as e:
        print(f"Error in game_reset: {str(e)}")

@socketio.on('game_ended')
def handle_game_ended():
    emit('game_ended', room=ROOM, namespace='/')

@socketio.on('force_update')
def handle_force_update():
    # Trigger a client-side fetch to ensure state is updated
    socketio.emit('force_fetch', {}, room=ROOM, namespace='/')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
