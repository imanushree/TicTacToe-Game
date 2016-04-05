"""api.py - Create and configure the Game API exposing the resources.
This can also contain game logic. For more complex games it would be wise to
move game logic to another file. Ideally the API will be simple, concerned
primarily with communication to/from the API's users."""


import logging
import endpoints
from protorpc import remote, messages
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import User, Game, Score
from models import NewGameForm, GameForm, StringMessage, MakeMoveForm, GameForms
from models import ScoreForms, GameHistoryForm
from utils import get_by_urlsafe

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
GET_GAME_REQUEST = endpoints.ResourceContainer(
                   urlsafe_game_key=messages.StringField(1),)
MAKE_MOVE_REQUEST = endpoints.ResourceContainer(MakeMoveForm,
                    urlsafe_game_key=messages.StringField(1),)
USER_REQUEST = endpoints.ResourceContainer(user_name=messages.StringField(1),
                                           email=messages.StringField(2))
USERNAME_REQUEST = endpoints.ResourceContainer(user_name=messages.StringField(1))

MEMCACHE_MOVES_REMAINING = 'MOVES_REMAINING'

@endpoints.api(name='tictactoe', version='v1')
class TicTacToeApi(remote.Service):
    """Game API"""
    @endpoints.method(request_message=USER_REQUEST,
                      response_message=StringMessage,
                      path='user',
                      name='create_user',
                      http_method='POST')
    def create_user(self, request):
        """Create a User. Requires a unique username"""
        if User.query(User.name == request.user_name).get():
            raise endpoints.ConflictException(
                    'A User with that name already exists!')
        user = User(name=request.user_name, email=request.email)
        user.put()
        return StringMessage(message='User {} created!'.format(
                request.user_name))

    @endpoints.method(request_message=NEW_GAME_REQUEST,
                      response_message=GameForm,
                      path='game',
                      name='new_game',
                      http_method='POST')
    def new_game(self, request):
        """Creates new game"""
        player_x = User.query(User.name == request.player_x).get()
        player_o = User.query(User.name == request.player_o).get()
        if not player_x:
            raise endpoints.NotFoundException(
                    'A User with name {} does not exist!'.format(request.player_x))
        if not player_o:
            raise endpoints.NotFoundException(
                    'A User with name {} does not exist!'.format(request.player_o))
        if player_x == player_o:
            raise endpoints.BadRequestException('Game can be played by 2'
                                                ' different players only.')
        game = Game.new_game(player_x.key, player_o.key, request.player_x)

        # Use a task queue to update the average attempts remaining.
        # This operation is not needed to complete the creation of a new game
        # so it is performed out of sequence.
        taskqueue.add(url='/tasks/cache_average_moves')
        return game.to_form('Good luck playing TicTacToe!')

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='get_game',
                      http_method='GET')
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game and game.game_over == False:
            return game.to_form('Time to make a move!')
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=USERNAME_REQUEST,
                      response_message=GameForms,
                      path='game',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns the games the user is associated with"""
        user = User.query(User.name==request.user_name).get()
        if user:
            my_games = Game.query((Game.player_x==user.key or Game.player_o==user.key) and Game.game_over==False).fetch()
            if my_games:
                for game in my_games:
                return GameForms(items=[game.to_form(message="Active Game details") for game in my_games])
            else:
                return GameForms(items=[Game(message='There are no active games for this user.')])
        else:
            raise endpoints.BadRequestException('User does not exist')

    @endpoints.method(request_message=USERNAME_REQUEST,
                      response_message=GameForms,
                      path='game',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns the games the user is associated with"""
        user = User.query(User.name==request.user_name).get()
        if user:
            games_played = Game.query((Game.player_x==user.key or Game.player_o==user.key) and Game.game_over==True).count()
            games_won = Game.query((Game.winner==user.key) and Game.game_over==True).count()
            if games_played > 0:
                for game in my_games:
                return GameForms(items=[game.to_form(message="Active Game details") for game in my_games])
            else:
                return GameForms(items=[Game(message='There are no active games for this user.')])
        else:
            raise endpoints.BadRequestException('User does not exist')

    @endpoints.method(request_message=MAKE_MOVE_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_move',
                      http_method='PUT')
    def make_move(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game.game_over:
            return game.to_form('Game already over!')
        if game.is_cancelled:
            return game.to_form('Sorry but this game has been cancelled.')

        win_combinations = [
          # horizontal
          [0,1,2],
          [3,4,5],
          [6,7,8],
          # vertical
          [0,3,6],
          [1,4,7],
          [2,5,8],
          # diagonal
          [0,4,8],
          [2,4,6]
        ]

        if request.move not in range(1, 10):
            raise endpoints.BadRequestException('Wrong move. Move should be within 1 to 9')
        history = {}
        symbol = ''
        game.number_of_moves += 1
        if game.board[request.move - 1] == '-':
            if game.player_x.get().name == request.player_name:
                symbol = 'X'
                next_player = 'player_o'
                current_player_key = game.player_x
                indices, game = self.play_move(symbol, next_player, game, request)
            elif game.player_o.get().name == request.player_name:
                symbol = 'O'
                next_player = 'player_x'
                current_player_key = game.player_o
                indices, game = self.play_move(symbol, next_player, game, request)
            else:
                raise endpoints.BadRequestException('Your not a valid player for this game')

            history['Player'] = symbol
            history['Move'] = request.move
            history['Result'] = 'None'

            if game.number_of_moves >= 5:
                for combination in win_combinations:
                    if len(set(indices).intersection(combination)) == 3:
                        game.winner = request.player_name
                        game.next_turn = ""
                        history['Result'] = "Win! Game Over."
                        if current_player_key == game.player_x:
                            game.history.append(history)
                            game.end_game(current_player_key, game.player_o, True)
                        else:
                            game.history.append(history)
                            game.end_game(game.player_o, current_player_key, True)
                        return game.to_form('Congrats ! You have won!')

        else:
            raise endpoints.BadRequestException('Illegal move. That move has already been made')

        if game.number_of_moves == 9:
            game.message = "Game over. It was a tie!"
            history['Result'] = "Game over. It was a tie!"
            game.next_turn = ""
            game.end_game(game.player_x, game.player_o, False)

        game.history.append(history)
        game.put()
        return game.to_form('Come on, You can win this! Give it your best shot!')


    def play_move(self, symbol, next_player, game, request):
        if game.next_turn == request.player_name:
            game.board[request.move - 1] = symbol
            indices = [i for i, j in enumerate(game.board) if j == symbol]
            next_player_key = getattr(game, next_player)
            game.next_turn = next_player_key.get().name
            return indices, game
        else:
            raise endpoints.BadRequestException('This is not your turn!')

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameHistoryForm,
                      path='games/game_history',
                      name='game_history',
                      http_method='GET')
    def game_history(self, request):
        '''Returns the game history '''
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        return GameHistoryForm(game_history=','.join(str(element) for element in game.history))

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessage,
                      path='games/cancel',
                      name='cancel_game',
                      http_method='GET')
    def cancel_game(self, request):
        '''Cancels an ongoing game. Cannot cancel completed games'''
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if not game.game_over:
            game.is_cancelled = True
            game.put()
            return StringMessage(message='The game is cancelled.')
        else:
            raise endpoints.BadRequestException('Sorry, cannot cancel \
                                                completed games.')

    @endpoints.method(response_message=ScoreForms,
                      path='scores',
                      name='get_scores',
                      http_method='GET')
    def get_scores(self, request):
        """Return all scores"""
        return ScoreForms(items=[score.to_form() for score in Score.query()])

    @endpoints.method(request_message=USER_REQUEST,
                      response_message=ScoreForms,
                      path='scores/user/{user_name}',
                      name='get_user_scores',
                      http_method='GET')
    def get_user_scores(self, request):
        """Returns all of an individual User's scores"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                    'A User with that name does not exist!')
        scores = Score.query(Score.user == user.key)
        return ScoreForms(items=[score.to_form() for score in scores])

    @endpoints.method(response_message=StringMessage,
                      path='games/average_attempts',
                      name='get_average_moves_remaining',
                      http_method='GET')
    def get_average_attempts(self, request):
        """Get the cached average moves remaining"""
        return StringMessage(message=memcache.get(MEMCACHE_MOVES_REMAINING) or '')

    @staticmethod
    def _cache_average_moves():
        """Populates memcache with the average moves remaining of Games"""
        games = Game.query(Game.game_over == False).fetch()
        if games:
            count = len(games)
            total_moves_remaining = sum([9 - game.number_of_moves
                                        for game in games])
            average = float(total_moves_remaining)/count
            memcache.set(MEMCACHE_MOVES_REMAINING,
                         'The average moves remaining is {:.2f}'.format(average))


api = endpoints.api_server([TicTacToeApi])
