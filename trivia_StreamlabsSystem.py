#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
# ---------------------------------------
# Libraries and references
# ---------------------------------------
import codecs
import io
import json
import os
import time
from datetime import datetime
from math import ceil

# ---------------------------------------
# [Required] Script information
# ---------------------------------------
ScriptName = "Trivia"
Website = "https://twitch.tv/crimdahl"
Creator = "Crimdahl"
Version = "1.1.0-Beta"
Description = "Trivia Minigame"
# ---------------------------------------
# Versions
# ---------------------------------------
""" Most recent Release
1.0-Beta    Initial beta release
1.0.1-Beta  Fixed Unhandled Exception in NextQuestion
1.0.2-Beta  Added question cooldown randomization - three new settings under Question Settings
            Removed question cooldown text from question reward text
            Renamed duration_between_questions to cooldown_between_questions
            Applied strip() in answer detection to prevent erroneous spaces from preventing accurate detection
            Checked current_questions_length before posting to chat in a couple of places. Don't want to tell people
                questions are ready when questions do not exist.
            Reformatted a lot of code to be PEP-8 compliant
1.0.3-Beta  Added option to disable display of the question's time of arrival with !trivia.
1.1.0-Beta  Added support for an arbitrary number of winners. Removed arena mode because it is now obsolete.
            Added grace period options to Reward Options. This grace period ends the question a certain period
                of time after a successful answer if multiple winners are allowed AND the maximum number of 
                winners has not been reached. Lets multiple people win, but cuts the question off quickly 
                to avoid spamming and copycat guessing.
            Removed unused debug code.
            Significant changes to setting parameters.
            More PEP-8 compliance changes.
"""
# ---------------------------------------
# Global Variables
# ---------------------------------------
path_to_script = os.path.abspath(os.path.dirname(__file__))
settings_file = os.path.join(path_to_script, "settings.json")
questions_file = os.path.join(path_to_script, "questions.json")
log_file = os.path.join(path_to_script, "trivialog.txt")
current_question_file = os.path.join(path_to_script, "currentquestion.txt")

master_questions_list = []  # List of all questions
current_questions_list = []  # List of currently active questions depending on settings
# Connects the master list to current list, required for question list modifications to work
question_index_map = []

current_question_index = -1  # Index in current_questions_list of the current question
current_question_points = 0  # Current question points, used when random scaling is in effect
current_game = ""  # Current game, as returned by an API call
question_start_time = time.time()  # What time does the next question start?
ready_for_next_question = True  # Boolean used when questions do not automatically start.
readiness_notification_time = time.time()
question_expiry_time = 0  # How many minutes questions last
# How long should the script go between the last file update and the next file update
next_question_file_update_time = 0
grace_period_used = False  # Tracks if the grace period has started for this question

correct_users_dict = {}  # Dictionary of users that gave correct answers, used in multi-reward mode

active = True  # Is the script running?
script_settings = None  # Settings variable
twitch_api_source = "https://decapi.me/twitch/game/"  # The source for getting current_game


# ---------------------------------------
# Classes
# ---------------------------------------
class Settings(object):
    def __init__(self, settings_file=None):
        if settings_file and os.path.isfile(settings_file):
            with codecs.open(settings_file, encoding="utf-8-sig", mode="r") as f:
                self.__dict__ = json.load(f, encoding="utf-8")
        else:
            # General
            self.run_only_when_live = True
            self.permissions_players = "Everyone"
            self.permissions_admins = "Moderator"

            # Question Settings
            self.duration_of_questions = 5
            self.cooldown_between_questions = 5
            self.randomize_question_cooldown = False
            self.question_cooldown_random_lower_bound = 0
            self.question_cooldown_random_upper_bound = 0
            self.automatically_run_next_question = True
            self.question_ask_string = "Win $points $currency by answering: $index) In $game, $question"
            self.question_reward_string = "$winnerlist answered correctly and won $points $currency."
            self.question_expiration_string = "Nobody answered the previous question. The answers were: $answers."
            self.question_file_ask_string = "$timeremaining) In $game, $question"
            self.question_file_reward_string = "$winnerlist answered correctly and won $points $currency."
            self.question_file_expiration_string = "Nobody answered the previous question. The answers were: $answers."

            # Trivia Rewards
            self.number_of_winners = 1
            self.enable_points_dividing = True
            self.enable_loyalty_point_rewards = True
            self.default_loyalty_point_value = 10
            self.reward_scaling = False
            self.point_value_random_lower_bound = 0
            self.point_value_random_upper_bound = 0
            self.percent_loyalty_point_value_increase_on_unanswered = 0
            self.percent_loyalty_point_value_decrease_on_answered = 0
            self.enable_grace_period = False
            self.grace_period_duration_in_seconds = 1

            # Output Settings
            self.display_next_question_time = False
            self.create_current_question_file = False
            self.debug_level = "Warn"
            self.enable_file_logging = False

            # Game Detection Settings
            self.enable_game_detection = False
            self.twitch_channel_name = ""

    def Reload(self, json_data):
        self.__dict__ = json.loads(json_data, encoding="utf-8")
        return

    def Save(self, settings_file):
        try:
            with codecs.open(settings_file, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8")
        except IOError as e:
            log("Settings Save: Failed to save settings to the file: "
                + str(e), LoggingLevel.str_to_int.get("Fatal"))
            raise e
        return


class Question(object):
    # Object-specific Variables
    points = None
    game = None
    question = None
    answers = []

    def __init__(self, **kwargs):
        self.points = kwargs["points"] if "points" in kwargs else script_settings.default_loyalty_point_value
        self.game = kwargs["game"] if "game" in kwargs \
            else Question.raise_value_error(self, "Error: No 'game' keyword was supplied.")
        self.question = kwargs["question"] if "question" in kwargs \
            else Question.raise_value_error(self, "Error, no 'question' keyword was supplied.")
        self.answers = kwargs["answers"] if "answers" in kwargs \
            else Question.raise_value_error(self, "Error: No 'answers' keyword was supplied.")

    def as_string(self):
        return "For " + str(self.points) + " " + Parent.GetCurrencyName() + ": In " + self.game + ", " + self.question

    def toJSON(self):
        return {"Points": self.points, "Game": self.game, "Question": self.question, "Answers": self.answers}

    def get_game(self):
        return self.game

    def set_game(self, new_game):
        self.game = new_game

    def get_question(self):
        return self.question

    def set_question(self, new_question):
        self.question = new_question

    def get_points(self):
        return self.points

    def set_points(self, new_points):
        self.points = new_points

    def get_answers(self):
        return self.answers

    def set_answers(self, new_answers):
        if isinstance(new_answers, list):
            self.answers = new_answers
            return True
        else:
            return False

    def remove_answer(self, answer):
        try:
            self.answers.remove(answer.lower())
            return True
        except ValueError:
            return False

    def add_answer(self, answer):
        if answer.lower() in (answer.lower() for answer in self.answers):
            return False
        else:
            self.answers.append(answer.lower())
            return True

    def raise_value_error(self, error_text):
        raise ValueError(error_text)

    def __str__(self):
        return "Game: " + self.game + ", Question: " + self.question


class LoggingLevel:
    str_to_int = {
        "All": 1,
        "Debug": 2,
        "Info": 3,
        "Warn": 4,
        "Fatal": 5,
        "Nothing": 6
    }
    int_to_string = {
        1: "All",
        2: "Debug",
        3: "Info",
        4: "Warn",
        5: "Fatal",
        6: "Nothing"
    }

    def __str__(self):
        return str(self.value)


# ---------------------------------------
# Functions
# ---------------------------------------
#   [Required] Initialize Data (Only called on load)
def Init():
    global script_settings
    global current_game
    global question_expiry_time
    script_settings = Settings(settings_file)
    script_settings.Save(settings_file)
    script_settings.cooldown_between_questions = max(script_settings.cooldown_between_questions, 0)
    script_settings.duration_of_questions = max(script_settings.duration_of_questions, 0)
    question_expiry_time = script_settings.duration_of_questions * 60

    if script_settings.enable_game_detection:
        if script_settings.twitch_channel_name == "":
            log("Init: Game Detection has been enabled without being supplied a Twitch Username.",
                LoggingLevel.str_to_int.get("Fatal"))
            raise AttributeError("Game Detection has been enabled without being supplied a Twitch Username.")
        # Log("Init: Game detection is enabled. Identifying most recent game.", LoggingLevel.str_to_int.get("Debug"))
        current_game = json.loads(Parent.GetRequest(twitch_api_source + script_settings.twitch_channel_name, {})).get(
            "response")
        log("Init: Most recent game identified as " + str(current_game) + ".", LoggingLevel.str_to_int.get("Info"))
    load_trivia()
    log("Init: Trivia Minigame Loaded", LoggingLevel.str_to_int.get("Info"))
    return


# Function that runs every time the Trivia command is used
def Execute(data):
    global active
    global current_question_index
    user_id = get_user_id(data.RawData)

    # Algorithm to start trivia if the trivia has been paused. Requires admin permission.
    if not active:
        if (Parent.HasPermission(data.User, script_settings.permissions_admins,
                                 "") or user_id == "216768170") and data.Message == "!trivia start":
            active = True
            log("Trivia Start: Started with Command.", LoggingLevel.str_to_int.get("Info"))
            post("Trivia started.")

    # If (the streamer is live OR trivia can run when offline) and trivia is active...
    if (Parent.IsLive() or not script_settings.run_only_when_live) and active and data.IsChatMessage():
        # Check if the chatter has administrator permissions. If so, see if they are running an admin command.
        if str(data.Message).startswith("!trivia") and (
                Parent.HasPermission(data.User, script_settings.permissions_admins,
                                     "") or user_id == "216768170") and data.GetParamCount() > 0:
            subcommand = data.GetParam(1)
            global current_game
            global master_questions_list
            global current_questions_list
            if subcommand == "stop":
                active = False
                update_current_question_file("")
                log("Trivia Stop: Stopped with Command.", LoggingLevel.str_to_int.get("Info"))
                post("Trivia stopped.")

            elif subcommand == "count":
                # Return a count of the number of questions available
                if script_settings.enable_game_detection:
                    # Also include the number of questions currently matching the game
                    post("Total questions: " + str(
                        len(master_questions_list)) + ". Questions from " + current_game + ": " + str(
                        len(current_questions_list)) + ".")
                else:
                    post("Number of questions available: " + str(len(master_questions_list)) + ".")

            elif subcommand == "answers":
                if current_question_index == -1:
                    post("No questions are currently loaded.")
                else:
                    post("Answers to the current question: " + ", ".join(
                        current_questions_list[current_question_index].get_answers()))

            elif subcommand == "save":
                if save_trivia():
                    post("Trivia saved.")

            elif subcommand == "load":
                if data.GetParamCount() == 2 and len(current_questions_list) > 0:
                    next_question()
                    # No confirmation necessary - if a question is loaded successfully the result will be obvious
                elif data.GetParamCount() == 3:
                    try:
                        question_index = int(data.GetParam(2)) - 1
                        if question_index < 0 or question_index > len(current_questions_list) - 1:
                            raise IndexError("Question index out of bounds.")
                        # Log("!Trivia Load: Called with supplied index.", LoggingLevel.str_to_int.get("Debug"))
                        next_question(question_index)
                    except (ValueError, IndexError) as e:
                        log("Trivia Load: Question could not be loaded: " + str(e), LoggingLevel.str_to_int.get("Warn"))
                        post("Error loading question. Was the supplied index a number and between 1 and " + str(
                            len(current_questions_list)) + "?")
                else:
                    log("Trivia Load: Subcommand used, but no questions exist that can be loaded.",
                        LoggingLevel.str_to_int.get("Info"))
                    post("Cannot load questions - no questions exist.")

            elif subcommand == "add":
                if data.GetParamCount() == 2:
                    post("Syntax: !trivia add (game:<Game Name>,) (points:<Points>,) "
                         "question:<Question>, answers:<Pipe-Separated List of Answers>")
                else:
                    # Get all of the required attributes from the message
                    # Try/catch to make sure points was convertible to an int
                    try:
                        new_points = int(get_attribute("points", data.Message))
                    except ValueError:
                        log("Trivia Add: No point value was supplied. Using the default point value.",
                            LoggingLevel.str_to_int.get("Debug"))
                        new_points = script_settings.default_loyalty_point_value

                    try:
                        new_game = get_attribute("game", data.Message)
                    except ValueError:
                        # If the attribute is not found, check for a current game, otherwise display an error
                        if not current_game == "":
                            new_game = current_game
                        else:
                            log("Trivia Add: Question not added. No game attribute detected in command call.",
                                LoggingLevel.str_to_int.get("Warn"))
                            post("Error: No game attribute detected. Please supply a game name.")
                            return

                    try:
                        new_question_text = get_attribute("question", data.Message)
                    except ValueError:
                        # If the attribute is not found, display an error
                        log("Trivia Add: Question not added. No question attribute detected in command call.",
                            LoggingLevel.str_to_int.get("Warn"))
                        post("Error: No question attribute detected.")
                        return

                    try:
                        new_answers = get_attribute("answers", data.Message).split("|")
                    except ValueError:
                        # If the attribute is not found, display an error
                        log("Trivia Add: Question not added. No answers attribute detected in command call.",
                            LoggingLevel.str_to_int.get("Warn"))
                        post("Error: No answers attribute detected. A question cannot be added without valid answers.")
                        return

                    # strip all whitespace from the beginning and ends of the answers
                    i = 0
                    while i < len(new_answers):
                        new_answers[i] = new_answers[i].strip()
                        i = i + 1

                    # create the Question object and add it to the list of questions,
                    #   then save the new list of questions
                    new_question = Question(game=new_game, points=new_points, question=new_question_text,
                                            answers=new_answers)
                    master_questions_list.append(new_question)
                    if not script_settings.enable_game_detection:
                        current_questions_list.append(new_question)
                    elif current_game == new_question.get_game():
                        current_questions_list.append(new_question)
                        question_index_map.append(len(master_questions_list) - 1)
                    if save_trivia():
                        log("Trivia Add: A new question has been added.", LoggingLevel.str_to_int.get("Info"))
                        post("Question added.")

            elif subcommand == "remove":
                if data.GetParamCount() == 2:
                    post("Syntax: !trivia remove <Question Index>")
                else:
                    try:
                        question_index = int(data.GetParam(2)) - 1
                        old_question = current_questions_list.pop(question_index)

                        if script_settings.enable_game_detection:
                            # Remove the question from the master question list using the index mapping
                            master_questions_list.pop(question_index_map[question_index])

                            # Pop the question out of the question_index_map, since it no longer exists
                            # For each remaining entry in the question_index_map, we need to reduce
                            #   indexes by one to reflect that a question was removed from the master list
                            question_index_map.pop(question_index)
                            question_index_map[question_index:] = [index - 1 for index in
                                                                   question_index_map[question_index:]]
                        else:
                            master_questions_list.pop(question_index)
                        if question_index == current_question_index:
                            current_question_index = -1
                        if save_trivia():
                            log("Trivia Remove: A question has been removed: " + str(old_question),
                                LoggingLevel.str_to_int.get("Info"))
                            post("Question removed.")
                    except (ValueError, IndexError) as e:
                        log("Trivia Remove: Question could not be removed: " + str(e),
                            LoggingLevel.str_to_int.get("Warn"))
                        post("Error removing question. Was the supplied index a number and between 1 and " + str(
                            len(current_questions_list)) + "?")

            elif subcommand == "modify":
                if data.GetParamCount() == 2:
                    post("Syntax: !trivia modify <Question Index> (game:<New Value>,) (question:<New Value>,) "
                         "(points:<New Value>,) (answers <add/remove/set>: <New Value>|<New Value>| ...)")
                else:
                    # Parameter two indicates the index of the question
                    try:
                        question_index = int(data.GetParam(2)) - 1
                    except ValueError:
                        # If parameter three was not an integer, display an error message
                        log("Trivia Modify: Trivia Modify subcommand supplied a non-integer question index.",
                            LoggingLevel.str_to_int.get("Warn"))
                        post("Error: The supplied index was not a number.")
                        return

                    changes = False
                    new_game = None
                    new_question = None
                    new_points = None
                    new_answer_set = None
                    new_answers = None
                    old_answers = None
                    if "game:" in data.Message:
                        new_game = get_attribute("game", data.Message)
                    if "question:" in data.Message:
                        new_question = get_attribute("question", data.Message)
                    if "points:" in data.Message:
                        new_points = get_attribute("points", data.Message)
                    if "answers set:" in data.Message:
                        new_answer_set = get_attribute("answers set", data.Message).split(",")
                    else:
                        if "answers add:" in data.Message:
                            new_answers = get_attribute("answers add", data.Message).split(",")
                        if "answers remove:" in data.Message:
                            old_answers = get_attribute("answers remove", data.Message).split(",")

                    if new_game:
                        current_questions_list[question_index].set_game(new_game)
                        if script_settings.enable_game_detection:
                            log("Trivia Modify: A question's game is being modified with Enable Game Detection Mode. "
                                "Master Question List Index "
                                + str(question_index_map[question_index]) +
                                ". Current Question List Index " + str(question_index) + ".",
                                LoggingLevel.str_to_int.get("Debug"))
                            master_questions_list[question_index_map[question_index]].set_game(new_game)
                        else:
                            log("Trivia Modify: A question's game is being modified without Enable Game Detection Mode."
                                " Master Question List Index "
                                + str(question_index_map[question_index]) +
                                ". Current Question List Index " + str(question_index) + ".",
                                LoggingLevel.str_to_int.get("Debug"))
                            master_questions_list[question_index].set_game(new_game)
                        changes = True
                    if new_question:
                        current_questions_list[question_index].set_question(new_question)
                        if script_settings.enable_game_detection:
                            log("Trivia Modify: A question's question is being modified with Enable Game Detection "
                                "Mode. Master Question List Index "
                                + str(question_index_map[question_index]) +
                                ". Current Question List Index " + str(question_index) + ".",
                                LoggingLevel.str_to_int.get("Debug"))
                            master_questions_list[question_index_map[question_index]].set_question(new_question)
                        else:
                            log("Trivia Modify: A question's question is being modified without Enable Game Detection"
                                " Mode. Master Question List Index "
                                + str(question_index_map[question_index]) +
                                ". Current Question List Index " + str(question_index) + ".",
                                LoggingLevel.str_to_int.get("Debug"))
                            master_questions_list[question_index].set_question(new_question)
                        changes = True
                    if new_points:
                        try:
                            current_questions_list[question_index].set_points(int(new_points))
                            if script_settings.enable_game_detection:
                                log("Trivia Modify: A question's value is being modified with Enable Game Detection"
                                    " Mode. Master Question List Index "
                                    + str(question_index_map[question_index]) +
                                    ". Current Question List Index " + str(question_index) + ".",
                                    LoggingLevel.str_to_int.get("Debug"))
                                master_questions_list[question_index_map[question_index]].set_points(int(new_points))
                            else:
                                log("Trivia Modify: A question's value is being modified without Enable Game Detection"
                                    " Mode. Master Question List Index "
                                    + str(question_index_map[question_index]) +
                                    ". Current Question List Index " + str(question_index) + ".",
                                    LoggingLevel.str_to_int.get("Debug"))
                                master_questions_list[question_index].set_points(int(new_points))
                            changes = True
                        except ValueError as e:
                            log("Trivia Modify: Trivia Modify subcommand supplied a non-integer point value.",
                                LoggingLevel.str_to_int.get("Warn"))
                            post(
                                "Error: The supplied point value was not a number. "
                                "The question's point value was not changed.")
                    if new_answer_set:
                        current_questions_list[question_index].set_answers(new_answer_set)
                        if script_settings.enable_game_detection:
                            log("Trivia Modify: A question's answer set is being modified with Enable Game Detection"
                                " Mode. Master Question List Index "
                                + str(question_index_map[question_index]) +
                                ". Current Question List Index " + str(question_index) + ".",
                                LoggingLevel.str_to_int.get("Debug"))
                            master_questions_list[question_index_map[question_index]].set_answers(new_answer_set)
                        else:
                            log("Trivia Modify: A question's answer set is being modified with Enable Game Detection"
                                " Mode. Master Question List Index "
                                + str(question_index_map[question_index]) +
                                ". Current Question List Index " + str(question_index) + ".",
                                LoggingLevel.str_to_int.get("Debug"))
                            master_questions_list[question_index].set_answers(new_answer_set)
                        changes = True
                    else:
                        current_answers_current = current_questions_list[question_index].get_answers()
                        if script_settings.enable_game_detection:
                            current_answers_master = master_questions_list[
                                question_index_map[question_index]].get_answers()
                        else:
                            current_answers_master = master_questions_list[question_index].get_answers()
                        if new_answers:
                            for answer in new_answers:
                                if answer not in current_answers_current:
                                    current_answers_current.append(answer)
                                    current_answers_current.sort()
                                    current_answers_master.append(answer)
                                    current_answers_master.sort()
                                    changes = True
                        if old_answers:
                            for answer in old_answers:
                                if answer in current_answers_current:
                                    current_answers_current.remove(answer)
                                    current_answers_master.remove(answer)
                                    changes = True

                    if changes:
                        if save_trivia():
                            post("Question modified.")
        elif str(data.Message).startswith("!trivia") and not (
                Parent.HasPermission(data.User, script_settings.permissions_admins,
                                     "") or user_id == "216768170") and data.GetParamCount() > 0:
            log(data.UserName + " attempted to use trivia admin commands without permission. " + str(data.Message),
                LoggingLevel.str_to_int.get("Info"))
            post(data.UserName + ", you do not have the permissions to use this command.")
        if Parent.HasPermission(data.User, script_settings.permissions_players, "") or user_id == "216768170":
            if str(data.Message) == "!trivia":
                global question_start_time
                global question_expiry_time
                if len(current_questions_list) == 0:
                    log("!Trivia: Called to start new question, but no questions exist.",
                        LoggingLevel.str_to_int.get("Warn"))
                    post("Could not load trivia. No questions exist.")
                elif current_question_index == -1:
                    if (not script_settings.automatically_run_next_question) and ready_for_next_question:
                        log("!Trivia: Called to start new question.", LoggingLevel.str_to_int.get("Debug"))
                        global next_question_file_update_time
                        global readiness_notification_time
                        next_question()
                        next_question_file_update_time = time.time()
                        readiness_notification_time = time.time()
                    else:
                        log("!Trivia: There is no active trivia question.", LoggingLevel.str_to_int.get("Info"))
                        if script_settings.display_next_question_time:
                            post("There is no active trivia question. The next trivia question arrives in " + str(
                                datetime.fromtimestamp(question_start_time - time.time()).strftime(
                                    '%M minutes and %S seconds.')))
                        else:
                            post("There is no active trivia question.")
                else:
                    post(parse_string(script_settings.question_ask_string) + " Time remaining: " + str(
                        datetime.fromtimestamp(question_expiry_time - time.time()).strftime(
                            '%M minutes and %S seconds.')))
            elif current_question_index != -1:
                check_for_match(data)


# Function that runs continuously
def Tick():
    global question_start_time
    global question_expiry_time
    global next_question_file_update_time
    global active
    if active and (not script_settings.run_only_when_live or (script_settings.run_only_when_live and Parent.IsLive())):
        # If time has expired, check to see if there is a current question
        # If there is a current question, depending on settings the answers
        #   may need to be displayed and the points adjusted
        current_time = time.time()
        global current_question_index

        if not current_question_index == -1:
            # There is a current question
            if current_time > question_expiry_time:
                # The question has expired. End the question.
                log("Tick: Question time exceeded. Ending question.", LoggingLevel.str_to_int.get("Debug"))
                end_question()
            elif script_settings.create_current_question_file and (current_time > next_question_file_update_time):
                # The question has not expired. Display the question and the remaining time.
                update_current_question_file(parse_string(script_settings.question_file_ask_string), 1)

        else:
            # There is no current question
            if current_time > question_start_time:
                # It is time for the next question.
                if script_settings.automatically_run_next_question:
                    # If the settings indicate to run the next question, do so.
                    log("Tick: Starting next question.", LoggingLevel.str_to_int.get("Debug"))
                    next_question()
                else:
                    # If the settings indicate to NOT run the next question,
                    #   set the boolean and display that the next question is ready.
                    global ready_for_next_question
                    global readiness_notification_time
                    ready_for_next_question = True
                    if script_settings.create_current_question_file:
                        update_current_question_file("The next question is ready! Type !trivia to begin.",
                                                     time.time() + 86400)
                    elif current_time > readiness_notification_time:
                        if len(current_questions_list) > 0:
                            post("The next question is ready! Type !trivia to begin.")
                        readiness_notification_time = time.time() + (10 * 60)
            elif script_settings.create_current_question_file and (current_time > next_question_file_update_time):
                # It is not time for the next question. Display the remaining time until the next question.
                update_current_question_file("Time until next question: " + str(
                    datetime.fromtimestamp(question_start_time - time.time()).strftime('%M:%S')) + ".", 1)


def check_for_match(data):
    global current_question_index
    try:
        current_question = current_questions_list[current_question_index]
        current_answers = current_question.get_answers()
        for answer in current_answers:
            if data.Message.lower().strip() == answer.lower().strip():
                # We have a match. Add them to the dictionary of correct users,
                #   then check to see if the question needs to be ended.
                correct_users_dict[data.User] = data.UserName
                log("CheckForMatch: Match detected between answer " + answer + " and message "
                    + data.Message + ". User " + data.UserName + " added to the list of correct users.",
                    LoggingLevel.str_to_int.get("Debug"))

                # Check to see if the maximum number of winners has been met
                if 0 < script_settings.number_of_winners <= len(correct_users_dict):
                    log("CheckForMatch: Number of winners achieved. Ending question.",
                        LoggingLevel.str_to_int.get("Debug"))
                    # If it has, immediately end the question
                    end_question()
                else:
                    # If the maximum number of winners has not been met, but the grace period is being
                    #   used, apply the grace period to end the question if it has not already been applied
                    if script_settings.enable_grace_period:
                        global grace_period_used
                        if not grace_period_used:
                            global question_expiry_time
                            question_expiry_time = time.time() + script_settings.grace_period_duration_in_seconds
                            grace_period_used = True
    except IndexError:
        current_question_index = -1


def end_question():
    global current_question_index
    global question_start_time

    # First, check to see if there is an active question. If there is no active question, nothing needs to be done.
    if not current_question_index == -1:
        # Check to see if there were any correct answers.
        if len(correct_users_dict) > 0:
            log("EndQuestion: Winners detected. Distributing points.", LoggingLevel.str_to_int.get("Debug"))
            # Iterate through the correct users dictionary
            correct_usernames = []
            for user_ID in correct_users_dict.keys():
                # If users are getting loyalty point rewards, reward the winners
                if script_settings.enable_loyalty_point_rewards:
                    # Determine if points are being divided amongst winners
                    if script_settings.enable_points_dividing:
                        Parent.AddPoints(user_ID,
                                         correct_users_dict[user_ID],
                                         ceil(current_question_points / len(correct_users_dict)))
                        log("EndQuestion: Adding "
                            + str(ceil(current_question_points / len(correct_users_dict)))
                            + " " + Parent.GetCurrencyName() + " to user " + correct_users_dict[user_ID] + "."
                            , LoggingLevel.str_to_int.get("Debug"))
                    else:
                        Parent.AddPoints(user_ID,
                                         correct_users_dict[user_ID],
                                         current_question_points)
                        log("EndQuestion: Adding "
                            + str(current_question_points)
                            + " " + Parent.GetCurrencyName() + " to user " + correct_users_dict[user_ID] + "."
                            , LoggingLevel.str_to_int.get("Debug"))
                correct_usernames.append(correct_users_dict[user_ID])
            correct_usernames.sort()    # Sort the list of winning usernames alphabetically

            # Reduce the reward for that question, if desired
            if script_settings.percent_loyalty_point_value_decrease_on_answered > 0:
                # Get the question's current points.
                question_points = current_questions_list[current_question_index].get_points()
                # Determine the new points by multiplying the current points by a multiplier.
                new_points = int(question_points - (question_points * (
                        script_settings.percent_loyalty_point_value_decrease_on_answered / 100.0)))
                # Assign the new value.
                current_questions_list[current_question_index].set_points(new_points)
                log("EndQuestion: Reducing points for question at index " + str(current_question_index + 1) + " by " +
                    str(script_settings.percent_loyalty_point_value_decrease_on_answered) + " percent. (" + str(
                    question_points) + " - " +
                    str(int(question_points
                            * (script_settings.percent_loyalty_point_value_decrease_on_answered
                               / 100.0))) + " = " + str(new_points) + ")"
                    , LoggingLevel.str_to_int.get("Debug"))
                save_trivia()

            # Post message rewarding users
            if script_settings.create_current_question_file:
                update_current_question_file(
                    parse_string(string=script_settings.question_file_reward_string,
                                 winners=correct_usernames), 10)
            else:
                if script_settings.cooldown_between_questions > 0:
                    post(parse_string(string=script_settings.question_reward_string,
                                      winners=correct_usernames))
                else:
                    post(parse_string(string=script_settings.question_reward_string, winners=correct_usernames))
        else:
            # No winners were detected. Display expiration message.
            if script_settings.create_current_question_file:
                update_current_question_file(parse_string(string=script_settings.question_expiration_string), 10)
            else:
                post(parse_string(string=script_settings.question_expiration_string))

            # Increase the reward for that question, if desired.
            if int(script_settings.percent_loyalty_point_value_increase_on_unanswered) > 0:
                # Get the question's current points.
                question_points = current_questions_list[current_question_index].get_points()
                # Determine the new points by multiplying the current points by a multiplier.
                new_points = int(question_points + question_points * (
                        script_settings.percent_loyalty_point_value_increase_on_unanswered / 100.0))
                # Assign the new value.
                current_questions_list[current_question_index].set_points(new_points)
                log("EndQuestion: Increasing points for question at index " + str(current_question_index + 1) + " by " +
                    str(script_settings.percent_loyalty_point_value_increase_on_unanswered) + " percent. (" + str(
                    question_points) + " + " +
                    str(int(question_points
                            * (script_settings.percent_loyalty_point_value_increase_on_unanswered
                               / 100.0))) + " = " + str(new_points) + ")"
                    , LoggingLevel.str_to_int.get("Debug"))
                save_trivia()
        correct_users_dict.clear()  # Clear the winners dictionary for use with the next question

    # End current question and set the next question's start time.
    current_question_index = -1
    random_cooldown_multiplier = 1
    if script_settings.randomize_question_cooldown:
        if script_settings.question_cooldown_random_upper_bound > script_settings.question_cooldown_random_lower_bound:
            random_cooldown_multiplier = \
                float(Parent.GetRandom(script_settings.question_cooldown_random_lower_bound,
                                       script_settings.question_cooldown_random_upper_bound)) / 100
        elif script_settings.question_cooldown_random_lower_bound > script_settings.question_cooldown_random_upper_bound:
            random_cooldown_multiplier = \
                float(Parent.GetRandom(script_settings.question_cooldown_random_upper_bound,
                                       script_settings.question_cooldown_random_lower_bound)) / 100
        else:
            random_cooldown_multiplier = script_settings.point_value_random_lower_bound
    question_start_time = time.time() + (script_settings.cooldown_between_questions * 60 * random_cooldown_multiplier)

    global ready_for_next_question
    global grace_period_used
    grace_period_used = False
    ready_for_next_question = False


def next_question(question_index=-1):
    global current_questions_list

    # Check to see if questions exist
    if len(current_questions_list) > 0:
        global current_question_index
        global question_expiry_time
        global ready_for_next_question
        global current_game
        global current_question_points

        if script_settings.enable_game_detection:
            # If the user is using game detection, check to see if
            # their game has changed before loading the next question
            if script_settings.twitch_channel_name == "":
                log("NextQuestion: Game Detection has been enabled without being supplied a Twitch Username.",
                    LoggingLevel.str_to_int.get("Fatal"))
                raise AttributeError("Game Detection has been enabled without being supplied a Twitch Username.")
            previous_game = current_game
            current_game = json.loads(
                Parent.GetRequest(twitch_api_source + script_settings.twitch_channel_name, {})).get("response")

            # If their active game has changed, reload the current question list
            if not previous_game == current_game:
                log("NextQuestion: Game change detected. New game is " + str(
                    current_game) + ". Loading new question set.", LoggingLevel.str_to_int.get("Info"))
                load_trivia()

        # Log the previous question to prevent duplicates
        previous_question_index = current_question_index

        # Start up a new question, avoiding using the same question twice in a row if possible
        if question_index == -1:
            if previous_question_index != -1 and len(current_questions_list) > 1:
                while True:
                    current_question_index = Parent.GetRandom(0, len(current_questions_list))
                    if current_question_index != previous_question_index:
                        break
            else:
                current_question_index = Parent.GetRandom(0, len(current_questions_list))
        else:
            current_question_index = question_index

        # If random point scaling is in effect, determine the point reward here
        if str(script_settings.reward_scaling).lower() == "random":
            # Perform some conditionals to make sure that everything works no matter
            #   which numbers are entered in which box
            if script_settings.point_value_random_upper_bound > script_settings.point_value_random_lower_bound:
                random_value_multiplier = float(Parent.GetRandom(script_settings.point_value_random_lower_bound,
                                                                 script_settings.point_value_random_upper_bound)) / 100
            elif script_settings.point_value_random_lower_bound > script_settings.point_value_random_upper_bound:
                random_value_multiplier = float(Parent.GetRandom(script_settings.point_value_random_upper_bound,
                                                                 script_settings.point_value_random_lower_bound)) / 100
            else:
                random_value_multiplier = script_settings.point_value_random_lower_bound
            current_question_points = int(
                ceil(current_questions_list[current_question_index].get_points() * random_value_multiplier))
        else:
            current_question_points = current_questions_list[current_question_index].get_points()

        # If we are not logging to a file, post the question in chat. File display is handled by tick().
        if not script_settings.create_current_question_file:
            post(parse_string(string=script_settings.question_ask_string))

        # Set the question expiration time
        question_expiry_time = time.time() + (script_settings.duration_of_questions * 60)
        log("NextQuestion: Next Question at " + datetime.fromtimestamp(question_expiry_time).strftime('%H:%M:%S') + ".",
            LoggingLevel.str_to_int.get("Debug"))
        ready_for_next_question = False
    else:
        # If questions do not exist, try again every 60 seconds
        global question_start_time
        log("NextQuestion: No questions exist. Trying again in 60 seconds.", LoggingLevel.str_to_int.get("Warn"))
        question_start_time = time.time() + 60


def get_attribute(attribute, message):
    log("GetAttribute: Called with message \"" + message + "\" looking for attribute \"" + attribute + "\".",
        LoggingLevel.str_to_int.get("Debug"))
    attribute = attribute.lower() + ":"
    # The start index of the attribute begins at the end of the attribute designator, such as "game:"
    try:
        index_of_beginning_of_attribute = message.lower().index(attribute) + len(attribute)
        log("GetAttribute: Attribute found at index " + str(index_of_beginning_of_attribute),
            LoggingLevel.str_to_int.get("Debug"))
    except ValueError as e:
        log("GetAttribute: The attribute was not found in the message.", LoggingLevel.str_to_int.get("Debug"))
        if attribute.lower() == "points=":
            return script_settings.default_loyalty_point_value
        raise e
    # The end index of the attribute is at the last space
    #   before the next attribute designator, or at the end of the message
    try:
        index_of_end_of_attribute = \
            message[index_of_beginning_of_attribute:
                    index_of_beginning_of_attribute + message[index_of_beginning_of_attribute:].index(":")].rindex(",")
    except ValueError:
        # If this error is thrown, the end of the message was hit, so just return all of the remaining message
        return message[index_of_beginning_of_attribute:].strip()
    result = message[index_of_beginning_of_attribute:index_of_beginning_of_attribute
                     + index_of_end_of_attribute].strip().strip(",")
    return result


def parse_string(string, points=-1, winners=[]):
    # Apply question attributes to a string
    global current_question_index
    if points == -1:
        points = current_questions_list[current_question_index].get_points()

    # Replace the $index parameter with the index of the current question
    string = string.replace("$index", str(current_question_index + 1))

    # Replace the $currency parameter with the name of the channel's currency
    string = string.replace("$currency", str(Parent.GetCurrencyName()))

    # Replace the $question parameter with the text of the current question
    string = string.replace("$question", current_questions_list[current_question_index].get_question())

    # Replace the $pointswon parameter with the points won by each person
    if script_settings.enable_loyalty_point_rewards and len(correct_users_dict) > 0:
        if script_settings.enable_points_dividing:
            # If people loyalty point rewards are enabled and
            string = string.replace("$pointswon", str(abs(current_question_points / len(correct_users_dict))))
        else:
            string = string.replace("$pointswon", str(current_question_points))
    else:
        # If nobody is winning points, replace with 0
        string = string.replace("$pointswon", "0")

    # Replace the $points parameter with the points of the current question
    string = string.replace("$points", str(current_question_points))

    # Replace the $answers parameter with a list of correct answers for the current question
    string = string.replace("$answers", ", ".join(current_questions_list[current_question_index].get_answers()))

    # Replace the $game parameter with the game of the current question
    string = string.replace("$game", current_questions_list[current_question_index].get_game())

    # Replace the $winnerspossible parameter with the number of possible winners
    string = string.replace("$winnerspossible", str(script_settings.number_of_winners))

    # Replace the $winnercount parameter with the number of actual winners
    string = string.replace("$winnercount", str(len(correct_users_dict)))

    # Replace the $winnerlist parameter with a list of users that answered the current question correctly
    if len(winners) > 2:
        string = string.replace("$winnerlist", ', '.join(winners[:-1]) + ", and " + str(winners[-1]))
    elif len(winners) == 2:
        string = string.replace("$winnerlist", ' and '.join(winners))
    elif winners:
        string = string.replace("$winnerlist", winners[0])

    # Replace the $timeremaining parameter with hte remaining time of the current question
    global question_expiry_time
    string = string.replace("$timeremaining",
                            str(datetime.fromtimestamp(question_expiry_time - time.time()).strftime(
                                '%M minutes and %S seconds')))

    # Replace the $time parameter with the time between questions
    string = string.replace("$time", str(datetime.fromtimestamp(question_start_time
                                                                - time.time()).strftime('%M minutes and %S seconds.')))
    return string


def save_trivia():
    try:
        # if the trivia file does not exist, create it
        if not os.path.exists(questions_file):
            with io.open(questions_file, 'w') as outfile:
                outfile.write(json.dumps({}))
            log("SaveTrivia: The trivia file was not found. A new one was created.",
                LoggingLevel.str_to_int.get("Warn"))

        # record the questions
        with open(questions_file, 'w') as outfile:
            outfile.seek(0)
            # When writing the Questions to disk, use the Question.toJSON() function
            json.dump(master_questions_list, outfile, indent=4, default=lambda q: q.toJSON())
            outfile.truncate()
            log("SaveTrivia: The trivia file was successfully updated.", LoggingLevel.str_to_int.get("Debug"))

        return True

    except IOError as e:
        log("SaveTrivia: Unable to save trivia questions: " + str(e), LoggingLevel.str_to_int.get("Fatal"))
        raise e


def load_trivia():
    # Check if the length of the master questions list is 0. If it is, we need to load questions.
    global master_questions_list
    if len(master_questions_list) == 0:
        # If the question list is empty, we need to load trivia from file. First, check if the file exists.
        if os.path.exists(questions_file):
            try:
                with io.open(questions_file) as infile:
                    object_data = json.load(infile)  # Load the json data

                # For each object/question in the object_data, create new questions
                #   and feed them to the master_questions_list
                # If game detection is off, feed them to the g
                global master_questions_list
                global current_questions_list
                global current_game
                for question in object_data:
                    new_question = Question(game=question["Game"],
                                            points=question["Points"],
                                            question=question["Question"],
                                            answers=question["Answers"])
                    master_questions_list.append(new_question)
            except ValueError:
                log("LoadTrivia: Question file exists, but contained no data.", LoggingLevel.str_to_int.get("Warn"))
        else:
            log("LoadTrivia: No questions file exists.", LoggingLevel.str_to_int.get("Warn"))

    # Check if the length of the master questions list is greater than 0.
    if len(master_questions_list) > 0:
        del current_questions_list[:]
        del question_index_map[:]
        # If the length of the master questions list is greater than 0, we can check if the user is using game detection
        if not script_settings.enable_game_detection:
            # User is not using game detection. Copy the master list to the current questions list
            current_questions_list = master_questions_list[:]
        elif script_settings.enable_game_detection:
            # User is using game detection. Iterate over the master list to get games matching their current game.
            for i in range(len(master_questions_list)):
                if master_questions_list[i].get_game() == current_game:
                    current_questions_list.append(master_questions_list[i])
                    question_index_map.append(i)
    log("LoadTrivia: Questions loaded into master list: " + str(
        len(master_questions_list)) + ". Questions currently being used: " + str(len(current_questions_list)),
        LoggingLevel.str_to_int.get("Info"))


# Reload Settings (Called when a user clicks the Save Settings button in the Chatbot UI)
def ReloadSettings(jsonData):
    # Execute json reloading here
    log("ReloadSettings: Saving settings from Chatbot UI...", LoggingLevel.str_to_int.get("Info"))
    global script_settings
    global current_question_index
    previous_game_detection = script_settings.enable_game_detection
    previous_duration_of_questions = script_settings.duration_of_questions
    previous_cooldown_between_questions = script_settings.cooldown_between_questions
    script_settings.__dict__ = json.loads(jsonData)
    script_settings.Save(settings_file)

    # If the user disabled the usage of the script file, empty the file so the on screen display goes away
    if not script_settings.create_current_question_file:
        update_current_question_file("")

    # If the duration of a question changed and there was a question active, we need to adjust the time accordingly
    if not current_question_index == -1 and not previous_duration_of_questions == script_settings.duration_of_questions:
        global question_expiry_time
        question_expiry_time = question_expiry_time + (
                script_settings.duration_of_questions - previous_duration_of_questions) * 60

    # If the duration between questions changed and there is no question active, we need to adjust the time accordingly
    if current_question_index == -1 and \
            not previous_cooldown_between_questions == script_settings.cooldown_between_questions:
        global question_start_time
        question_start_time = question_start_time + (
                script_settings.cooldown_between_questions - previous_cooldown_between_questions) * 60

    # If the user has toggled game detection, reload the current question list and update current game
    if not previous_game_detection == script_settings.enable_game_detection:
        global current_game
        if not script_settings.enable_game_detection:
            current_game = ""
            log("ReloadSettings: Game Detection deactivated. Reloading questions.", LoggingLevel.str_to_int.get("Info"))
        else:
            current_game = json.loads(
                Parent.GetRequest(twitch_api_source + script_settings.twitch_channel_name, {})).get("response")
            log("ReloadSettings: Game Detection activated. Most recent game identified as " + str(
                current_game) + ". Reloading questions.", LoggingLevel.str_to_int.get("Info"))

        load_trivia()

    log("ReloadSettings: Settings saved and applied successfully", LoggingLevel.str_to_int.get("Info"))


def log(message, level=LoggingLevel.str_to_int.get("All")):
    if script_settings.enable_file_logging:
        global log_file
        file = open(log_file, "a+")
        file.writelines(str(datetime.now()).ljust(26) + " " + str(LoggingLevel.int_to_string.get(level) + ":").ljust(
            10) + message + "\n")
        file.close()
    if LoggingLevel.str_to_int.get(script_settings.debug_level) <= level:
        Parent.Log(ScriptName, "(" + str(LoggingLevel.int_to_string.get(level)) + ") " + message)


def post(message):
    Parent.SendStreamMessage(message)


def update_current_question_file(line=None, duration_in_seconds=1):
    global current_question_file
    global next_question_file_update_time
    file = open(current_question_file, "w+")
    file.seek(0)
    if line:
        file.write("Trivia: " + line)
    file.truncate()
    file.close()
    next_question_file_update_time = time.time() + duration_in_seconds


def get_user_id(raw_data):
    # Retrieves the user ID of a Twitch chatter using the raw data returned from Twitch
    try:
        raw_data = raw_data[raw_data.index("user-id=") + len("user-id="):]
        raw_data = raw_data[:raw_data.index(";")]
    except Exception:
        return ""
    return raw_data
