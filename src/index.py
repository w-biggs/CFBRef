import os
import logging.handlers
import traceback
from datetime import datetime
from datetime import timedelta

import static
import utils
import wiki
import counters
import messages
import file_utils
from classes import Action

log = logging.getLogger("bot")

games = {}


def init():
	global games
	games = {}
	count_games = 0
	for gameFile in os.listdir(static.SAVE_FOLDER_NAME):
		game = reloadAndReturn(gameFile)
		if game is not None:
			count_games += 1
			changed = False
			for team in [game.home, game.away]:
				wikiTeam = wiki.getTeamByTag(team.tag)
				if ((team.coaches > wikiTeam.coaches) - (team.coaches < wikiTeam.coaches)) != 0:
					log.debug("Coaches for game {}, team {} changed from {} to {}".format(
						game.thread,
						team.tag,
						team.coaches,
						wikiTeam.coaches
					))
					changed = True
					team.pastCoaches.extend(team.coaches)
					team.coaches = wikiTeam.coaches

			if changed:
				try:
					if len(game.previousStatus):
						log.debug("Reverting status and reprocessing {}".format(game.previousStatus[0].messageId))
						utils.revertStatus(game, 0)
						file_utils.saveGameObject(game)
						messages.reprocessPlay(game, game.status.messageId)
					else:
						log.info("Coaches changed, but game has no plays, not reprocessing")

					game = reloadAndReturn(game.thread)
				except Exception as err:
					log.warning(traceback.format_exc())
					log.warning("Unable to revert game when changing coaches")

			games[game.thread] = game

	counters.active_games.set(count_games)


def getAllGames():
	allGames = []
	for thread in games:
		allGames.append(games[thread])
	allGames.sort(key=utils.gameSortValue)
	return allGames


def addNewGame(game):
	games[game.thread] = game
	counters.active_games.inc()


def reloadAndReturn(thread, alwaysReturn=False):
	game = file_utils.loadGameObject(thread)
	if game is None:
		return None
	for team in [game.home, game.away]:
		if team.conference == "":
			team.conference = None
		if not hasattr(team, "css_tag"):
			team.css_tag = None
	if game.status.waitingAction != Action.END:
		games[game.thread] = game
		return game
	elif alwaysReturn:
		return game
	else:
		return None


def getGamesPastPlayclock():
	pastPlayclock = []
	for thread in games:
		game = games[thread]
		if not game.errored and game.playclock < datetime.utcnow():
			pastPlayclock.append(game)
	return pastPlayclock


def getGamesPastPlayclockWarning():
	pastPlayclock = []
	for thread in games:
		game = games[thread]
		if not game.errored and not game.playclockWarning and game.playclock - timedelta(hours=12) < datetime.utcnow():
			pastPlayclock.append(game)
	return pastPlayclock


def endGame(game):
	if game.thread in games:
		del games[game.thread]
	file_utils.archiveGameFile(game.thread)
	counters.active_games.dec()
	wiki.updateTeamsWiki()


def setGameErrored(game):
	game.errored = True
	game.playclock = datetime.utcnow()


def clearGameErrored(game):
	game.errored = False
	game.deadline = game.deadline + (datetime.utcnow() - game.playclock)
	game.playclock = datetime.utcnow() + timedelta(hours=24)


def getGameFromTeamTag(tag):
	for thread in games:
		game = games[thread]
		if game.home.tag == tag or game.away.tag == tag:
			return game
	return None
