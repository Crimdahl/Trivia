#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
#---------------------------------------
# Libraries and references
#---------------------------------------
import os, io, json, codecs, time
from enum import Enum
from datetime import datetime
from math import ceil

#---------------------------------------
# [Required] Script information
#---------------------------------------
ScriptName = "Trivia"
Website = "https://twitch.tv/crimdahl"
Creator = "Crimdahl"
Version = ".1"
Description = "Trivia Minigame"
#---------------------------------------
# Versions
#---------------------------------------
""" Most recent Release
.1  

"""
#---------------------------------------
# Global Variables
#---------------------------------------
path_to_script = os.path.abspath(os.path.dirname(__file__))
settings_file = os.path.join(path_to_script, "settings.json")
questions_file = os.path.join(path_to_script, "questions.json")
log_file = os.path.join(path_to_script, "trivialog.txt")
current_question_file = os.path.join(path_to_script, "currentquestion.txt")

master_questions_list = []      #List of all questions
current_questions_list = []     #List of currently active questions depending on settings
question_index_map = []         #Connects the master list to current list, required for question list modifications to work

current_question_index = -1         #Index in current_questions_list of the current question
current_question_points = 0         #Current question points, used when random scaling is in effect
current_game = ""                   #Current game, as returned by an API call
question_start_time = time.time()   #What time does the next question start?
ready_for_next_question = True      #Boolean used when questions do not automatically start.
readiness_notification_time = time.time()
question_expiry_time = 0            #How many minutes questions last
next_question_file_update_time = 0  #How long should the script go between the last file update and the next file update

correct_users_dict = {}             #Dictionary of users that gave correct answers, used in Arena Mode

active = True                       #Is the script running?
script_settings = None              #Settings variable
twitch_api_source = "https://decapi.me/twitch/game/"    #The source for getting current_game

#---------------------------------------
# Classes
#---------------------------------------
class Settings(object):
    def __init__(self, settings_file=None):
        if settings_file and os.path.isfile(settings_file):
            with codecs.open(settings_file, encoding="utf-8-sig", mode="r") as f:
                self.__dict__ = json.load(f, encoding="utf-8")
        else:
            #General
            self.run_only_when_live = True
            self.permissions_players = "Everyone"
            self.permissions_admins = "Moderator"

            #Question Settings
            self.duration_of_questions = 5
            self.duration_between_questions = 5
            self.automatically_run_next_question = True
            self.question_ask_string = "Win $points $currency by answering: $index) In $game, $question"
            self.question_reward_string = "$users has answered correctly and won $points $currency."
            self.question_expiration_string = "Nobody answered the previous question. The answers were: $answers."

            #Arena Mode Settings
            self.enable_arena_mode = False
            self.enable_arena_points_dividing = False

            #Trivia Rewards
            self.enable_loyalty_point_rewards = True
            self.default_loyalty_point_value = 10
            self.reward_scaling = False
            self.point_value_random_lower_bound = 0
            self.point_value_random_upper_bound = 0
            self.percent_loyalty_point_value_increase_on_unanswered = 0
            self.percent_loyalty_point_value_decrease_on_answered = 0

            #Output Settings
            self.create_current_question_file = False
            self.debug_level = "Warn"
            self.enable_file_logging = False

            #Game Detection Settings
            self.enable_game_detection = False
            self.twitch_channel_name = ""
            


    def Reload(self, jsondata):
        self.__dict__ = json.loads(jsondata, encoding="utf-8")
        return

    def Save(self, settings_file):
        try:
            with codecs.open(settings_file, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8")
        except IOError as e:
            Log("Settings Save: Failed to save settings to the file: " + str(e), LoggingLevel.Fatal)
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
        self.game = kwargs["game"] if "game" in kwargs else Question.raise_value_error(self, "Error: No 'game' keyword was supplied.")
        self.question = kwargs["question"] if "question" in kwargs else Question.raise_value_error(self, "Error, no 'question' keyword was supplied.")
        self.answers = kwargs["answers"] if "answers" in kwargs else Question.raise_value_error(self, "Error: No 'answers' keyword was supplied.")

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

class LoggingLevel(Enum):
    def __str__(self):
        return str(self.value)

    All = 1
    Debug = 2
    Info = 3
    Warn = 4
    Fatal = 5
    Nothing = 6

#---------------------------------------
# Functions
#---------------------------------------
#   [Required] Initialize Data (Only called on load)
def Init():
    global script_settings
    global current_game
    script_settings = Settings(settings_file)
    script_settings.Save(settings_file)
    script_settings.duration_between_questions = max(script_settings.duration_between_questions, 0)
    script_settings.duration_of_questions = max(script_settings.duration_of_questions, 0)
    if script_settings.enable_game_detection:
        if script_settings.twitch_channel_name == "":
            Log("Init: Game Detection has been enabled without being supplied a Twitch Username.", LoggingLevel.Fatal)
            raise AttributeError("Game Detection has been enabled without being supplied a Twitch Username.")
        #Log("Init: Game detection is enabled. Identifying most recent game.", LoggingLevel.Debug)
        current_game = json.loads(Parent.GetRequest(twitch_api_source + script_settings.twitch_channel_name, {})).get("response")
        Log("Init: Most recent game identified as " + str(current_game) + ".", LoggingLevel.Info)
    LoadTrivia()
    Log("Init: Trivia Minigame Loaded", LoggingLevel.Info)
    return

#Function that runs every time the Trivia command is used
def Execute(data):
    global active
    global current_question_index
    user_id = GetUserID(data.RawData)

    #Algorithm to start trivia if the trivia has been paused. Requires admin permission.
    if not active:
        if (Parent.HasPermission(data.User, script_settings.permissions_admins, "") or user_id == "216768170") and data.Message == "!trivia start":
            active = True
            Log("Trivia Start: Started with Command.", LoggingLevel.Info)
            Post("Trivia started.")

    #If (the streamer is live OR trivia can run when offline) and trivia is active...
    if (Parent.IsLive() or not script_settings.run_only_when_live) and active and data.IsChatMessage():
        #Check if the chatter has administrator permissions. If so, see if they are running an admin command.
        if str(data.Message).startswith("!trivia") and (Parent.HasPermission(data.User, script_settings.permissions_admins, "") or user_id == "216768170") and data.GetParamCount() > 0:
            subcommand = data.GetParam(1)
            if subcommand == "stop":
                active = False
                UpdateCurrentQuestionFile("")
                Log("Trivia Stop: Stopped with Command.", LoggingLevel.Info)
                Post("Trivia stopped.")

            elif subcommand == "count":
                if script_settings.enable_game_detection:
                    Post("Total questions: " + str(len(master_questions_list)) + ". Questions from " + current_game + ": " + str(len(current_questions_list)) + ".")
                else:
                    Post("Number of questions available: " + str(len(master_questions_list)) + ".")

            elif subcommand == "answers":
                if current_question_index == -1:
                    Post("No questions are currently loaded.")
                else:
                    Post("Answers to the current question: " + ", ".join(current_questions_list[current_question_index].get_answers()))

            elif subcommand == "save":
                if SaveTrivia():
                    Post("Trivia saved.")

            elif subcommand == "load":
                if data.GetParamCount() == 2 and len(current_questions_list) > 0:
                    #Log("!Trivia Load: Called.", LoggingLevel.Debug)
                    NextQuestion()
                    #No confirmation necessary - if a question is loaded successfully the result will be obvious
                elif data.GetParamCount() == 3:
                    try:
                        question_index = int(data.GetParam(2)) - 1
                        if question_index < 0 or question_index > len(current_questions_list) - 1:
                            raise IndexError("Question index out of bounds.")
                        #Log("!Trivia Load: Called with supplied index.", LoggingLevel.Debug)
                        NextQuestion(question_index)
                    except (ValueError, IndexError) as e:
                        Log("Trivia Load: Question could not be loaded: " + str(e), LoggingLevel.Warn)
                        Post("Error loading question. Was the supplied index a number and between 1 and " + str(len(current_questions_list)) + "?")
                else:
                    Log("Trivia Load: Subcommand used, but no questions exist that can be loaded.", LoggingLevel.Info)
                    Post("Cannot load questions - no questions exist.")

            elif subcommand == "add":
                if data.GetParamCount() == 2:
                    Post("Syntax: !trivia add (game:<Game Name>,) (points:<Points>,) question:<Question>, answers:<Pipe-Separated List of Answers>")
                else:
                    #Get all of the required attributes from the message
                    #Try/catch to make sure points was convertible to an int
                    try:
                        new_points = int(GetAttribute("points", data.Message))
                    except ValueError:
                        Log("Trivia Add: No point value was supplied. Using the default point value.", LoggingLevel.Debug)
                        new_points = script_settings.default_loyalty_point_value

                    try:
                        new_game = GetAttribute("game", data.Message)
                    except ValueError:
                        #If the attribute is not found, check for a current game, otherwise display an error
                        if not current_game == "":
                            new_game = current_game
                        else:
                            Log("Trivia Add: Question not added. No game attribute detected in command call.", LoggingLevel.Warn)
                            Post("Error: No game attribute detected. Please supply a game name.")
                            return

                    try:
                        new_question_text = GetAttribute("question", data.Message)
                    except ValueError:
                        #If the attribute is not found, display an error
                        Log("Trivia Add: Question not added. No question attribute detected in command call.", LoggingLevel.Warn)
                        Post("Error: No question attribute detected.")
                        return

                    try:
                        new_answers = GetAttribute("answers", data.Message).split("|")
                    except ValueError:
                        #If the attribute is not found, display an error
                        Log("Trivia Add: Question not added. No answers attribute detected in command call.", LoggingLevel.Warn)
                        Post("Error: No answers attribute detected. A question cannot be added without valid answers.")
                        return

                    #strip all whitespace from the beginning and ends of the answers
                    i = 0
                    while i < len(new_answers):
                        new_answers[i] = new_answers[i].strip()
                        i = i + 1
                        
                    #create the Question object and add it to the list of questions, then save the new list of questions
                    global master_questions_list
                    global current_questions_list
                    global current_game
                    new_question = Question(game=new_game, points=new_points, question=new_question_text, answers=new_answers)
                    master_questions_list.append(new_question)
                    if not script_settings.enable_game_detection:
                        current_questions_list.append(new_question)
                    elif current_game == new_question.get_game():
                        current_questions_list.append(new_question)
                        question_index_map.append(len(master_questions_list) - 1)
                    if SaveTrivia():
                        Log("Trivia Add: A new question has been added.", LoggingLevel.Info)
                        Post("Question added.")
            
            elif subcommand == "remove":
                if data.GetParamCount() == 2:
                    Post("Syntax: !trivia remove <Question Index>")
                else:
                    try:
                        global master_questions_list
                        global current_questions_list
                        question_index = int(data.GetParam(2)) - 1
                        old_question = current_questions_list.pop(question_index)

                        if script_settings.enable_game_detection:
                            #Remove the question from the master question list using the index mapping
                            master_questions_list.pop(question_index_map[question_index])

                            #Pop the question out of the question_index_map, since it no longer exists
                            #For each remaining entry in the question_index_map, we need to reduce indexes by one to reflect that a question was removed from the master list
                            question_index_map.pop(question_index)
                            #Log("Number of indices after the question that was removed: " + str(len(question_index_map[question_index:])) + ".", LoggingLevel.Debug)
                            question_index_map[question_index:] = [index - 1 for index in question_index_map[question_index:]]
                        else:
                            #Log("Trivia Remove: A question is being removed without Enable Game Detection Mode. Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list.pop(question_index)
                        if question_index == current_question_index:
                            current_question_index = -1
                        if SaveTrivia():
                            Log("Trivia Remove: A question has been removed: " + str(old_question), LoggingLevel.Info)
                            Post("Question removed.")
                    except (ValueError, IndexError) as e:
                        Log("Trivia Remove: Question could not be removed: " + str(e), LoggingLevel.Warn)
                        Post("Error removing question. Was the supplied index a number and between 1 and " + str(len(current_questions_list)) + "?")

            elif subcommand == "modify":
                if data.GetParamCount() == 2:
                    Post("Syntax: !trivia modify <Question Index> (game:<New Value>,) (question:<New Value>,) (points:<New Value>,) (answers <add/remove/set>: <New Value>|<New Value>| ...)")
                else:
                    #Parameter two indicates the index of the question
                    try:
                        question_index = int(data.GetParam(2)) - 1
                    except ValueError:
                        #If parameter three was not an integer, display an error message
                        Log("Trivia Modify: Trivia Modify subcommand supplied a non-integer question index.", LoggingLevel.Warn)
                        Post("Error: The supplied index was not a number.")
                        return

                    global master_questions_list
                    global current_questions_list
                    changes = False
                    newGame = None
                    newQuestion = None
                    newPoints = None
                    newAnswerSet = None
                    newAnswers = None
                    oldAnswers = None
                    if "game:" in data.Message:
                        newGame = GetAttribute("game", data.Message)
                    if "question:" in data.Message:
                        newQuestion = GetAttribute("question", data.Message)
                    if "points:" in data.Message:
                        newPoints = GetAttribute("points", data.Message)
                    if "answers set:" in data.Message:
                        newAnswerSet = GetAttribute("answers set", data.Message).split(",")
                    else:
                        if "answers add:" in data.Message:
                            newAnswers = GetAttribute("answers add", data.Message).split(",")
                        if "answers remove:" in data.Message:
                            oldAnswers = GetAttribute("answers remove", data.Message).split(",")

                    if newGame: 
                        current_questions_list[question_index].set_game(newGame)
                        if script_settings.enable_game_detection:
                            Log("Trivia Modify: A question's game is being modified with Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list[question_index_map[question_index]].set_game(newGame)
                        else:
                            Log("Trivia Modify: A question's game is being modified without Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list[question_index].set_game(newGame)
                        changes = True
                    if newQuestion:
                        current_questions_list[question_index].set_question(newQuestion)
                        if script_settings.enable_game_detection:
                            Log("Trivia Modify: A question's question is being modified with Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list[question_index_map[question_index]].set_question(newQuestion)
                        else:
                            Log("Trivia Modify: A question's question is being modified without Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list[question_index].set_question(newQuestion)
                        changes = True
                    if newPoints:
                        try:
                            current_questions_list[question_index].set_points(int(newPoints))
                            if script_settings.enable_game_detection:
                                Log("Trivia Modify: A question's value is being modified with Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                        ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                                master_questions_list[question_index_map[question_index]].set_points(int(newPoints))
                            else:
                                Log("Trivia Modify: A question's value is being modified without Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                                master_questions_list[question_index].set_points(int(newPoints))
                            changes = True
                        except ValueError as e:
                            Log("Trivia Modify: Trivia Modify subcommand supplied a non-integer point value.", LoggingLevel.Warn)
                            Post("Error: The supplied point value was not a number. The question's point value was not changed.")
                    if newAnswerSet:
                        current_questions_list[question_index].set_answers(newAnswerSet)
                        if script_settings.enable_game_detection:
                            Log("Trivia Modify: A question's answer set is being modified with Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list[question_index_map[question_index]].set_answers(newAnswerSet)
                        else:
                            Log("Trivia Modify: A question's answer set is being modified with Enable Game Detection Mode. Master Question List Index " + str(question_index_map[question_index]) + 
                                    ". Current Question List Index " + str(question_index) + ".", LoggingLevel.Debug)
                            master_questions_list[question_index].set_answers(newAnswerSet)
                        changes = True
                    else:
                        current_answers_current = current_questions_list[question_index].get_answers()
                        if script_settings.enable_game_detection:
                            current_answers_master = master_questions_list[question_index_map[question_index]].get_answers()
                        else:
                            current_answers_master = master_questions_list[question_index].get_answers()
                        if newAnswers:
                            for answer in newAnswers:
                                if answer not in current_answers_current:
                                    current_answers_current.append(answer)
                                    current_answers_current.sort()
                                    current_answers_master.append(answer)
                                    current_answers_master.sort()
                                    changes = True
                        if oldAnswers:  
                            for answer in oldAnswers:
                                if answer in current_answers_current:
                                    current_answers_current.remove(answer)
                                    current_answers_master.remove(answer)
                                    changes = True
                    
                    if changes:
                        if SaveTrivia():
                            Post("Question modified.")
        elif str(data.Message).startswith("!trivia") and not (Parent.HasPermission(data.User, script_settings.permissions_admins, "") or user_id == "216768170") and data.GetParamCount() > 0:
            Log(data.UserName + " attempted to use trivia admin commands without permission. " + str(data.Message), LoggingLevel.Info)
            Post(data.UserName + ", you do not have the permissions to use this command.")
        if (Parent.HasPermission(data.User, script_settings.permissions_players, "") or user_id == "216768170"):
            if str(data.Message) == "!trivia":
                global question_start_time
                global question_expiry_time
                if current_question_index == -1:
                    if (not script_settings.automatically_run_next_question) and ready_for_next_question:
                        Log("!Trivia: Called to start new question.", LoggingLevel.Debug)
                        global next_question_file_update_time
                        global readiness_notification_time
                        NextQuestion()
                        next_question_file_update_time = time.time()
                        readiness_notification_time = time.time()
                    else:
                        Log("Trivia: There is no trivia question active.", LoggingLevel.Info)
                        Post("There are no active trivia questions. The next trivia question arrives in " + str(datetime.fromtimestamp(question_start_time - time.time()).strftime('%M minutes and %S seconds.')))
                else:
                    Post(ParseString(script_settings.question_ask_string) + " Time remaining: " + str(datetime.fromtimestamp(question_expiry_time - time.time()).strftime('%M minutes and %S seconds.')))
            elif current_question_index != -1:
                CheckForMatch(data)
            
#Function that runs continuously
def Tick():
    global question_start_time
    global question_expiry_time
    global next_question_file_update_time
    global active
    if active and (not script_settings.run_only_when_live or (script_settings.run_only_when_live and Parent.IsLive())):
        # If time has expired, check to see if there is a current question
        # If there is a current question, depending on settings the answers may need to be displayed and the points adjusted
        current_time = time.time()

        if not current_question_index == -1:
            #There is a current question
            if current_time > question_expiry_time:
                #The question has expired. End the question.
                global current_question_index
                Log("Tick: Question time exceeded. Ending question.", LoggingLevel.Debug)
                EndQuestion()
            elif script_settings.create_current_question_file and (current_time > next_question_file_update_time):
                #The question has not expired. Display the question and the remaining time.
                if script_settings.enable_arena_mode:
                    UpdateCurrentQuestionFile(ParseString(str(datetime.fromtimestamp(question_expiry_time - time.time()).strftime('%M:%S')) + ") In $game, $question"), 1)
                else:
                    UpdateCurrentQuestionFile(ParseString(str(datetime.fromtimestamp(question_expiry_time - time.time()).strftime('%M:%S')) + ") In $game, $question"), 1)
            
        else:
            #There is no current question
            if current_time > question_start_time:
                #It is time for the next question.
                if script_settings.automatically_run_next_question:
                    #If the settings indicate to run the next question, do so.
                    Log("Tick: Starting next question.", LoggingLevel.Debug)
                    NextQuestion()
                else:
                    #If the settings indicate to NOT run the next question, set the boolean and display that the next question is ready.
                    global ready_for_next_question
                    global readiness_notification_time
                    ready_for_next_question = True
                    if script_settings.create_current_question_file:
                        UpdateCurrentQuestionFile("The next question is ready! Type !trivia to begin.", time.time() + 86400)
                    elif current_time > readiness_notification_time: 
                        Post("The next question is ready! Type !trivia to begin.")
                        readiness_notification_time = time.time() + (10 * 60)
            elif script_settings.create_current_question_file and (current_time > next_question_file_update_time):
                #It is not time for the next question. Display the remaining time until the next question.
                UpdateCurrentQuestionFile("Time until next question: " + str(datetime.fromtimestamp(question_start_time - time.time()).strftime('%M:%S')) + ".", 1)

        #Log("Current time: " + str(current_time) + ". Update time: " + str(next_question_file_update_time))
        #if current_time > next_question_file_update_time:
            #Log("Tick: Updating Question File. Current time: " + str(current_time) + " vs " + str(next_question_file_update_time), LoggingLevel.Debug)
            #UpdateCurrentQuestionFile()
    return

def CheckForMatch(data):
    global current_question_index
    try:
        current_question = current_questions_list[current_question_index]
        current_answers = current_question.get_answers()
        for answer in current_answers:
            if data.Message.lower() == answer.lower():
                correct_users_dict[data.User] = data.UserName
                Log("CheckForMatch: Match detected between answer " + answer + " and message " + data.Message + ". User " + data.UserName + " added to the list of correct users.", LoggingLevel.Debug)
                if not script_settings.enable_arena_mode:
                    Log("CheckForMatch: Arena mode is not active. Ending question.", LoggingLevel.Debug)
                    EndQuestion()
                    return
            else:
                Log("CheckForMatch: No match detected between answer " + answer + " and message \"" + data.Message + "\".", LoggingLevel.Debug)
        Log("CheckForMatch: No match detected in the message from user " + data.UserName + ".", LoggingLevel.Debug)                  
        return False
    except IndexError:
        current_question_index = -1
        return False

def EndQuestion():
    global current_question_index
    if not current_question_index == -1:
        #Question is ending. Reward users, if desired
        if len(correct_users_dict) > 0:
            Log("EndQuestion: Winners detected. Distributing points.", LoggingLevel.Debug)
            #Get the number of points being rewarded
            points_being_rewarded = 0
            if script_settings.enable_loyalty_point_rewards:
                if str(script_settings.reward_scaling).lower() == "random":
                    global current_question_points
                    points_being_rewarded = current_question_points
                    #Log("EndQuestion: Random points rewarded by question: " + str(points_being_rewarded) + ".", LoggingLevel.Debug)
                else:
                    points_being_rewarded = current_questions_list[current_question_index].get_points()
                    #Log("EndQuestion: Base points rewarded by question: " + str(points_being_rewarded) + ".", LoggingLevel.Debug)
                if script_settings.enable_arena_points_dividing:
                    points_being_rewarded = points_being_rewarded / len(correct_users_dict)
                    #Log("EndQuestion: Divided points rewarded by question: " + str(points_being_rewarded) + ".", LoggingLevel.Debug)

            #Iterate through the correct users dictionary
            correct_usernames = []
            for user_ID in correct_users_dict.keys():
                if script_settings.enable_loyalty_point_rewards:
                    Parent.AddPoints(user_ID, correct_users_dict[user_ID], points_being_rewarded)
                    Log("EndQuestion: Adding " + str(points_being_rewarded) + " " + Parent.GetCurrencyName() + " to user " + correct_users_dict[user_ID] + ".", LoggingLevel.Debug)
                #Log("EndQuestion: Adding user ID " + str(user_ID) + " to the list of correct users with the username " + correct_users_dict[user_ID] + ".", LoggingLevel.Debug)
                correct_usernames.append(correct_users_dict[user_ID])
            correct_users_dict.clear()
            correct_usernames.sort()
            #Log("EndQuestion: Final correct users list for this reward: " + str(correct_usernames), LoggingLevel.Debug)

            #Reduce the reward for that question, if desired
            if script_settings.percent_loyalty_point_value_decrease_on_answered > 0:
                question_points = current_questions_list[current_question_index].get_points()
                new_points = int(question_points - (question_points * (script_settings.percent_loyalty_point_value_decrease_on_answered / 100.0)))
                current_questions_list[current_question_index].set_points(new_points)
                Log("EndQuestion: Reducing points for question at index " + str(current_question_index + 1) + " by " + 
                    str(script_settings.percent_loyalty_point_value_decrease_on_answered) + " percent. (" + str(question_points) + " - " + 
                    str(int(question_points * (script_settings.percent_loyalty_point_value_decrease_on_answered / 100.0))) + " = " + str(new_points) + ")", LoggingLevel.Debug)
                SaveTrivia()

            #Post message rewarding users
            if script_settings.enable_arena_mode:
                if script_settings.create_current_question_file:
                    global next_question_file_update_time
                    UpdateCurrentQuestionFile(ParseString(string = script_settings.question_reward_string, points = points_being_rewarded, users = correct_usernames), 10)
                else:
                    if script_settings.duration_between_questions > 0:
                        Post(ParseString(string = script_settings.question_reward_string, points = points_being_rewarded, users = correct_usernames) + " The next question will arrive in " + str(script_settings.duration_between_questions) + " minute(s).")
                    else:
                        Post(ParseString(string = script_settings.question_reward_string, points = points_being_rewarded, users = correct_usernames))
            else:
                if script_settings.create_current_question_file:
                    global next_question_file_update_time
                    UpdateCurrentQuestionFile(ParseString(string = script_settings.question_reward_string, points = points_being_rewarded, users = correct_usernames), 10)
                else:
                    if script_settings.duration_between_questions > 0: 
                        Post(ParseString(string = script_settings.question_reward_string, points = points_being_rewarded, users = correct_usernames) + " The next question will arrive in " + str(script_settings.duration_between_questions) + " minute(s).")
                    else:
                        Post(ParseString(string = script_settings.question_reward_string, points = points_being_rewarded, users = correct_usernames))
        else:
            #No winners were detected. Display expiration message.
            if script_settings.create_current_question_file:
                global next_question_file_update_time
                global question_start_time
                UpdateCurrentQuestionFile(ParseString(string = script_settings.question_expiration_string), 10)
            else:
                if script_settings.duration_between_questions > 0:
                    Post(ParseString(string = script_settings.question_expiration_string) + " The next question will arrive in " + str(script_settings.duration_between_questions) + " minute(s).")
                else:
                    Post(ParseString(string = script_settings.question_expiration_string))
            if int(script_settings.percent_loyalty_point_value_increase_on_unanswered) > 0:
                question_points = current_questions_list[current_question_index].get_points()
                new_points = int(question_points + question_points * (script_settings.percent_loyalty_point_value_increase_on_unanswered / 100.0))
                current_questions_list[current_question_index].set_points(new_points)
                Log("EndQuestion: Increasing points for question at index " + str(current_question_index + 1) + " by " + 
                    str(script_settings.percent_loyalty_point_value_increase_on_unanswered) + " percent. (" + str(question_points) + " + " + 
                    str(int(question_points * (script_settings.percent_loyalty_point_value_increase_on_unanswered / 100.0))) + " = " + str(new_points) + ")", LoggingLevel.Debug)
                SaveTrivia()
    current_question_index = -1
    global question_start_time
    global ready_for_next_question
    question_start_time = time.time() + (script_settings.duration_between_questions * 60)
    ready_for_next_question = False

def NextQuestion(question_index = -1):
    #Log("NextQuestion: Called with index of " + str(question_index) + ".", LoggingLevel.Debug)
    global current_question_index
    global question_expiry_time
    global ready_for_next_question
    global current_game
    global current_question_points

    if script_settings.enable_game_detection:
        #If the user is using game detection, check to see if their game has changed before loading the next question
        if script_settings.twitch_channel_name == "":
            Log("NextQuestion: Game Detection has been enabled without being supplied a Twitch Username.", LoggingLevel.Fatal)
            raise AttributeError("Game Detection has been enabled without being supplied a Twitch Username.")
        #Log("NextQuestion: Game detection is enabled. Identifying most recent game.", LoggingLevel.Debug)
        previous_game = current_game
        current_game = json.loads(Parent.GetRequest(twitch_api_source + script_settings.twitch_channel_name, {})).get("response")
        #Log("NextQuestion: Most recent game identified as " + str(current_game) + ".", LoggingLevel.Debug)

        #If their active game has changed, reload the current question list
        if not previous_game == current_game:
            Log("NextQuestion: Game change detected. New game is " + str(current_game) + ". Loading new question set.", LoggingLevel.Info)
            LoadTrivia()

    previous_question_index = -1
    previous_question_index = current_question_index  #Log the previous question to prevent duplicates 
    #Start up a new question, avoiding using the same question twice in a row
    if question_index == -1:
        if previous_question_index != -1 and len(current_questions_list) > 1:
            while True:
                current_question_index = Parent.GetRandom(0,len(current_questions_list))
                if current_question_index != previous_question_index: 
                    break
        else: 
            current_question_index = Parent.GetRandom(0,len(current_questions_list))
    else:
        current_question_index = question_index
    #Log("NextQuestion: Loaded question at Index " + str(current_question_index + 1) + ".", LoggingLevel.Debug)
    
    #If random point scaling is in effect, determine the point reward here
    if str(script_settings.reward_scaling).lower() == "random":
        #Log("NextQuestion: Points randomizing using range: " + str(float(script_settings.point_value_random_lower_bound) / 100) + "x to " + str(float(script_settings.point_value_random_upper_bound) / 100) + "x.", LoggingLevel.Debug)
        if script_settings.point_value_random_upper_bound > script_settings.point_value_random_lower_bound:
            random_value_multiplier = float(Parent.GetRandom(script_settings.point_value_random_lower_bound, script_settings.point_value_random_upper_bound)) / 100
        elif script_settings.point_value_random_lower_bound > script_settings.point_value_random_upper_bound:
            random_value_multiplier = float(Parent.GetRandom(script_settings.point_value_random_upper_bound, script_settings.point_value_random_lower_bound)) / 100
        else: 
            random_value_multiplier = script_settings.point_value_random_lower_bound
        #Log("NextQuestion: Question multiplier: " + str(random_value_multiplier) + "x.", LoggingLevel.Debug)
        current_question_points = int(ceil(current_questions_list[current_question_index].get_points() * random_value_multiplier))
        #Log("NextQuestion: Randomized points awarded by question: " + str(current_question_points) + ".", LoggingLevel.Debug)

    if not script_settings.create_current_question_file:
        if script_settings.enable_arena_mode:
            Post(ParseString(string = script_settings.question_ask_string))
        else:
            Post(ParseString(string = script_settings.question_ask_string))
    question_expiry_time = time.time() + ((script_settings.duration_of_questions) * 60)
    Log("NextQuestion: Next Question at " + datetime.fromtimestamp(question_expiry_time).strftime('%H:%M:%S') + ".", LoggingLevel.Debug)
    ready_for_next_question = False

def GetAttribute(attribute, message):
    Log("GetAttribute: Called with message \"" + message + "\" looking for attribute \"" + attribute + "\".", LoggingLevel.Debug)
    attribute = attribute.lower() + ":"
    #The start index of the attribute begins at the end of the attribute designator, such as "game:"
    try:
        index_of_beginning_of_attribute = message.lower().index(attribute) + len(attribute)
        Log("GetAttribute: Attribute found at index " + str(index_of_beginning_of_attribute), LoggingLevel.Debug)
    except ValueError as e:
        Log("GetAttribute: The attribute was not found in the message.", LoggingLevel.Debug)
        if attribute.lower() == "points=":
            #Log("GetAttribute: Default points are being applied.", LoggingLevel.Debug)
            return script_settings.default_loyalty_point_value
        raise e
    #The end index of the attribute is at the last space before the next attribute designator, or at the end of the message
    try:
        index_of_end_of_attribute = message[index_of_beginning_of_attribute:index_of_beginning_of_attribute + message[index_of_beginning_of_attribute:].index(":")].rindex(",")
    except ValueError:
        #If this error is thrown, the end of the message was hit, so just return all of the remaining message
        return message[index_of_beginning_of_attribute:].strip()
    result = message[index_of_beginning_of_attribute:index_of_beginning_of_attribute + index_of_end_of_attribute].strip().strip(",")
    #Log("GetAttribute: " + attribute + " successfully retrieved with a value of \"" + result + "\".", LoggingLevel.Debug)
    return result

def ParseString(string, points = -1, users = []):
    #Apply question attributes to a string
    global current_question_index
    if points == -1:
        points = current_questions_list[current_question_index].get_points()
    string = string.replace("$index", str(current_question_index + 1))
    string = string.replace("$currency", str(Parent.GetCurrencyName()))
    string = string.replace("$question", current_questions_list[current_question_index].get_question())
    if script_settings.enable_loyalty_point_rewards:
        if str(script_settings.reward_scaling).lower() == "random":
            global current_question_points
            string = string.replace("$points", str(current_question_points))
        else:
            string = string.replace("$points", str(points))
    else:
        string = string.replace("$points", "0")
    string = string.replace("$answers", ", ".join(current_questions_list[current_question_index].get_answers()))
    string = string.replace("$game", current_questions_list[current_question_index].get_game())
    string = string.replace("$users", ", ".join(users))
    string = string.replace("$time", str(script_settings.duration_of_questions))
    #Log("ParseString: Result of string parsing: \"" + string + "\"", LoggingLevel.Debug)
    return string

def SaveTrivia():
    try:        
        #if the trivia file does not exist, create it
        if not os.path.exists(questions_file):
            with io.open(questions_file, 'w') as outfile:
                outfile.write(json.dumps({}))
            Log("SaveTrivia: The trivia file was not found. A new one was created.", LoggingLevel.Warn)

        #record the questions
        with open (questions_file, 'w') as outfile:
            outfile.seek(0)
            #When writing the Questions to disk, use the Question.toJSON() function
            json.dump(master_questions_list, outfile, indent=4, default=lambda q: q.toJSON())
            outfile.truncate()
            Log("SaveTrivia: The trivia file was successfully updated.", LoggingLevel.Debug)
        
        return True

    except IOError as e:
        Log("SaveTrivia: Unable to save trivia questions: " + str(e), LoggingLevel.Fatal)
        raise e

def LoadTrivia():
    #Check if the length of the master questions list is 0. If it is, we need to load questions.
    global master_questions_list
    if len(master_questions_list) == 0:
        #If the question list is empty, we need to load trivia from file. First, check if the file exists.
        if os.path.exists(questions_file):
            try:
                with io.open(questions_file) as infile:
                    objectdata = json.load(infile)    #Load the json data

                #For each object/question in the objectdata, create new questions and feed them to the master_questions_list
                    #If game detection is off, feed them to the g
                global master_questions_list
                global current_questions_list
                global current_game
                for question in objectdata:
                    new_question = Question(game=question["Game"], points=question["Points"], question=question["Question"], answers=question["Answers"])
                    master_questions_list.append(new_question)
            except ValueError:
                Log("LoadTrivia: Question file exists, but contained no data.", LoggingLevel.Warn)
        else:
            Log("LoadTrivia: No questions file exists.", LoggingLevel.Warn)
    
    #Check if the length of the master questions list is greater than 0.
    if len(master_questions_list) > 0:
        del current_questions_list[:]
        del question_index_map[:]
        #If the length of the master questions list is greater than 0, we can check if the user is using game detection
        if not script_settings.enable_game_detection:
            #User is not using game detection. Copy the master list to the current questions list
            current_questions_list = master_questions_list[:]
        elif script_settings.enable_game_detection:
            #User is using game detection. Iterate over the master list to get games matching their current game.
            for i in range(len(master_questions_list)):
                if master_questions_list[i].get_game() == current_game:
                    current_questions_list.append(master_questions_list[i])
                    question_index_map.append(i)
    Log("LoadTrivia: Questions loaded into master list: " + str(len(master_questions_list)) + ". Questions currently being used: " + str(len(current_questions_list)), LoggingLevel.Info)
        
#Reload Settings (Called when a user clicks the Save Settings button in the Chatbot UI)
def ReloadSettings(jsonData):
    # Execute json reloading here
    Log("ReloadSettings: Saving settings from Chatbot UI...", LoggingLevel.Info)
    global script_settings
    global current_question_index
    previous_game_detection = script_settings.enable_game_detection
    previous_duration_of_questions = script_settings.duration_of_questions
    previous_duration_between_questions = script_settings.duration_between_questions
    script_settings.__dict__ = json.loads(jsonData)
    script_settings.Save(settings_file)

    #If the user disabled the usage of the script file, empty the file so the on screen display goes away
    if not script_settings.create_current_question_file:
        UpdateCurrentQuestionFile("")

    #If the duration of a question changed and there was a question active, we need to adjust the time accordingly
    if not current_question_index == -1 and not previous_duration_of_questions == script_settings.duration_of_questions:
        global question_expiry_time
        question_expiry_time = question_expiry_time + (script_settings.duration_of_questions - previous_duration_of_questions) * 60

    #If the duration between questions changed and there is no question active, we need to adjust the time accordingly
    if current_question_index == -1 and not previous_duration_between_questions == script_settings.duration_between_questions:
        global question_start_time
        question_start_time = question_start_time + (script_settings.duration_between_questions - previous_duration_between_questions) * 60

    #If the user has toggled game detection, reload the current question list and update current game
    if not previous_game_detection == script_settings.enable_game_detection:
        global current_game
        if not script_settings.enable_game_detection:
            current_game = ""
            Log("ReloadSettings: Game Detection deactivated. Reloading questions.", LoggingLevel.Info)
        else:
            current_game = json.loads(Parent.GetRequest(twitch_api_source + script_settings.twitch_channel_name, {})).get("response")
            Log("ReloadSettings: Game Detection activated. Most recent game identified as " + str(current_game) + ". Reloading questions.", LoggingLevel.Info)
        
        LoadTrivia()

    Log("ReloadSettings: Settings saved and applied successfully", LoggingLevel.Info)

def Log(message, level = LoggingLevel.All):
    if script_settings.enable_file_logging:
        global log_file
        file = open(log_file, "a+")
        file.writelines(str(datetime.now()).ljust(26) + " " + str(level.name + ":").ljust(10) + message + "\n")
        file.close()
    if LoggingLevel[script_settings.debug_level].value <= level.value:
        Parent.Log(ScriptName, "(" + str(level.name) + ") " + message)

def Post(message):
    Parent.SendStreamMessage(message)

def UpdateCurrentQuestionFile(line = None, duration_in_seconds = 1):
    global current_question_file
    global next_question_file_update_time
    file = open(current_question_file, "w+")
    file.seek(0)
    if line:
        file.write("Trivia: " + line)
    file.truncate()
    file.close()
    next_question_file_update_time = time.time() + duration_in_seconds

def GetUserID(rawdata):
    #Retrieves the user ID of a Twitch chatter using the raw data returned from Twitch
    try:
        rawdata = rawdata[rawdata.index("user-id=") + len("user-id="):]
        rawdata = rawdata[:rawdata.index(";")]
    except Exception:
        return ""
    return rawdata