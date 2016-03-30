"""api.py - Create and configure the Game API exposing the resources.
This can also contain game logic. For more complex games it would be wise to
move game logic to another file. Ideally the API will be simple, concerned
primarily with communication to/from the API's users."""


import logging
import endpoints
from protorpc import remote, messages
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import User, Game #, Score
from models import NewGameForm, GameForm, StringMessage, MakeMoveForm
# , ,\
#     ScoreForms
from utils import get_by_urlsafe

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
# GET_GAME_REQUEST = endpoints.ResourceContainer(
#         urlsafe_game_key=messages.StringField(1),)
MAKE_MOVE_REQUEST = endpoints.ResourceContainer(
    MakeMoveForm,
    urlsafe_game_key=messages.StringField(1),)
USER_REQUEST = endpoints.ResourceContainer(user_name=messages.StringField(1),
                                           email=messages.StringField(2))

# MEMCACHE_MOVES_REMAINING = 'MOVES_REMAINING'

@endpoints.api(name='guess_a_number', version='v1')
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
        # if not request.user_name:
        #     raise endpoints.BadRequestException('Please provide a user name')
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
        # try:
        game = Game.new_game(player_x.key, player_o.key, request.player_x)
        # except ValueError:
        #     raise endpoints.BadRequestException('Maximum must be greater '
        #                                         'than minimum!')

        # Use a task queue to update the average attempts remaining.
        # This operation is not needed to complete the creation of a new game
        # so it is performed out of sequence.
        # taskqueue.add(url='/tasks/cache_average_attempts')
        return game.to_form('Good luck playing TicTacToe!')

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='get_game',
                      http_method='GET')
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            return game.to_form('Time to make a move!')
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=MAKE_MOVE_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_move',
                      http_method='PUT')
    def make_move(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game.game_over:
            game.next_turn = ""
            return game.to_form('Game already over!')

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

        # if game.player_x != request.player_name and game.player_o != request.player_name:
        #     raise endpoints.BadRequestException('Your not a valid player for this game')

        if request.move not in range(1, 10):
            raise endpoints.BadRequestException('Wrong move. Move should be within 1 to 9')

        game.number_of_moves += 1
        if game.board[request.move - 1] == '-':
            if game.player_x.get().name == request.player_name:
                if game.next_turn == request.player_name:
                    game.board[request.move - 1] = 'X'
                    indices = [i for i, j in enumerate(game.board) if j == 'X']
                    game.next_turn = game.player_o.get().name
                else:
                    raise endpoints.BadRequestException('This is not your turn!')
            elif game.player_o.get().name == request.player_name:
                if game.next_turn == request.player_name:
                    game.board[request.move - 1] = 'O'
                    indices = [i for i, j in enumerate(game.board) if j == 'O']
                    game.next_turn = game.player_x.get().name
                else:
                    raise endpoints.BadRequestException('This is not your turn!')
            else:
                raise endpoints.BadRequestException('Your not a valid player for this game')

            if game.number_of_moves >= 5:
                for combination in win_combinations:
                    if len(set(indices).intersection(combination)) == 3:
                        game.winner = request.player_name
                        game.end_game(True)
                        winner = User.query(User.name == request.player_name).get()
                        winner.score += 1
                        winner.put()
                        return game.to_form('Congrats! You have won!')

        else:
            raise endpoints.BadRequestException('Illegal move. That move has already been made')

        if game.number_of_moves == 9:
            game.message = "Game over. It was a tie!"
            game.end_game('True')

        game.put()
        return game.to_form('Come on, You can win this! Give it your best shot!')







        # if request.guess == game.target:
        #     game.end_game(True)
        #     return game.to_form('You win!')

        # if request.guess < game.target:
        #     msg = 'Too low!'
        # else:
        #     msg = 'Too high!'

        # if game.attempts_remaining < 1:
        #     game.end_game(False)
        #     return game.to_form(msg + ' Game over!')
        # else:
        #     game.put()
        #     return game.to_form(msg)

    # @endpoints.method(response_message=ScoreForms,
    #                   path='scores',
    #                   name='get_scores',
    #                   http_method='GET')
    # def get_scores(self, request):
    #     """Return all scores"""
    #     return ScoreForms(items=[score.to_form() for score in Score.query()])

    # @endpoints.method(request_message=USER_REQUEST,
    #                   response_message=ScoreForms,
    #                   path='scores/user/{user_name}',
    #                   name='get_user_scores',
    #                   http_method='GET')
    # def get_user_scores(self, request):
    #     """Returns all of an individual User's scores"""
    #     user = User.query(User.name == request.user_name).get()
    #     if not user:
    #         raise endpoints.NotFoundException(
    #                 'A User with that name does not exist!')
    #     scores = Score.query(Score.user == user.key)
    #     return ScoreForms(items=[score.to_form() for score in scores])

    # @endpoints.method(response_message=StringMessage,
    #                   path='games/average_attempts',
    #                   name='get_average_attempts_remaining',
    #                   http_method='GET')
    # def get_average_attempts(self, request):
    #     """Get the cached average moves remaining"""
    #     return StringMessage(message=memcache.get(MEMCACHE_MOVES_REMAINING) or '')

    # @staticmethod
    # def _cache_average_attempts():
    #     """Populates memcache with the average moves remaining of Games"""
    #     games = Game.query(Game.game_over == False).fetch()
    #     if games:
    #         count = len(games)
    #         total_attempts_remaining = sum([game.attempts_remaining
    #                                     for game in games])
    #         average = float(total_attempts_remaining)/count
    #         memcache.set(MEMCACHE_MOVES_REMAINING,
    #                      'The average moves remaining is {:.2f}'.format(average))


api = endpoints.api_server([TicTacToeApi])
