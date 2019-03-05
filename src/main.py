#!/usr/bin/python3

import os
import logging.handlers
import time
import sys
import signal
import traceback

import globals
import reddit
import messages
import wiki
import utils
import state
import index
import file_utils
import string_utils
from classes import Action

### Logging setup ###
LOG_LEVEL = logging.DEBUG
if not os.path.exists(globals.LOG_FOLDER_NAME):
	os.makedirs(globals.LOG_FOLDER_NAME)
LOG_FILENAME = globals.LOG_FOLDER_NAME+"/"+"bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 256 * 64


class ContextFilter(logging.Filter):
	def filter(self, record):
		record.gameid = globals.logGameId
		return True


log = logging.getLogger("bot")
log.setLevel(LOG_LEVEL)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s:%(gameid)s %(message)s')
log_stdHandler = logging.StreamHandler()
log_stdHandler.setFormatter(log_formatter)
log.addHandler(log_stdHandler)
log.addFilter(ContextFilter())
if LOG_FILENAME is not None:
	log_fileHandler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=LOG_FILE_MAXSIZE, backupCount=LOG_FILE_BACKUPCOUNT)
	log_fileHandler.setFormatter(log_formatter)
	log.addHandler(log_fileHandler)


if not os.path.exists(globals.SAVE_FOLDER_NAME):
	os.makedirs(globals.SAVE_FOLDER_NAME)
if not os.path.exists(globals.ARCHIVE_FOLDER_NAME):
	os.makedirs(globals.ARCHIVE_FOLDER_NAME)


def signal_handler(signal, frame):
	log.info("Handling interupt")
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


log.debug("Connecting to reddit")

once = False
debug = False
user = None
if len(sys.argv) >= 2:
	user = sys.argv[1]
	for arg in sys.argv:
		if arg == 'once':
			once = True
		elif arg == 'debug':
			debug = True
		elif arg == 'shortQuarter':
			globals.quarterLength = 30
else:
	log.error("No user specified, aborting")
	sys.exit(0)


if not reddit.init(user):
	sys.exit(0)


wiki.loadPages()

index.init()

while True:
	try:
		for message in reddit.getMessageStream():
			startTime = time.perf_counter()
			log.debug("Processing message")
			wiki.loadPages()

			try:
				messages.processMessage(message)
			except Exception as err:
				log.warning("Error in main loop")
				log.warning(traceback.format_exc())
				if globals.game is not None:
					log.debug("Setting game {} as errored".format(globals.game.thread))
					index.setGameErrored(globals.game)
					file_utils.saveGameObject(globals.game)
					ownerMessage = string_utils.renderGameStatusMessage(globals.game)

					message.reply("This game has errored. Please wait for the bot owner to help.")
				else:
					ownerMessage = "Unable to process message from /u/{}, skipping".format(str(message.author))

				try:
					reddit.sendMessage(globals.OWNER, "NCFAA game errored", ownerMessage)
					message.mark_read()
				except Exception as err2:
					log.warning("Error sending error message")
					log.warning(traceback.format_exc())

			log.debug("Message processed after: %d", int(time.perf_counter() - startTime))
			utils.clearLogGameID()

			for game in index.getGamesPastPlayclock():
				state.executeDelayOfGame(game)

			for game in index.getGamesPastPlayclockWarning():
				warningText = "This is a warning that your [game]({}) is waiting on a reply from you to " \
								"this {}. You have 12 hours until a delay of game penalty."\
								.format(string_utils.getLinkToThread(game.thread),
				                        string_utils.getLinkFromGameThing(game.thread, utils.getPrimaryWaitingId(game.status.waitingId)))
				results = reddit.sendMessage(recipients=game.team(game.status.waitingOn).coaches,
									subject="{} vs {} 12 hour warning".format(game.away.name, game.home.name),
									message=warningText)
				log.debug("12 hour warning sent to {} for game {}: {}"
							.format(
							string_utils.getCoachString(game, game.status.waitingOn),
							game.thread,
							','.join([result.fullname for result in results])
						))
				game.playclockWarning = True
				file_utils.saveGameObject(game)

			utils.clearLogGameID()
			if once:
				break

	except Exception as err:
		log.warning("Hit an error in main loop")
		log.warning(traceback.format_exc())

	if once:
		break

	time.sleep(5 * 60)
