#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
#---------------------------------------
# Libraries and references
#---------------------------------------
import os, io, json, codecs, time
from enum import Enum
from datetime import datetime

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
questions_list = []
correct_users_dict = {}
current_question_index = -1
question_start_time = time.time()
question_expiry_time = 0
next_question_file_update_time = 0
active = True
ready_for_next_question = True
script_settings = None

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
            self.duration_of_questions = 5
            self.duration_between_questions = 5
            self.automatically_run_next_question = True
            self.show_answers_if_no_winners = False
            self.no_winners_response_string = "Nobody answered the previous question. The answers were: $answers."

            #Standard Mode Settings
            self.standard_question_ask_string = "Win $points $currency by answering: $index) In $game, $question"
            self.standard_question_reward_string = "$users has answered correctly and won $points $currency."

            #Arena Mode Settings
            self.enable_arena_mode = False
            self.enable_arena_points_dividing = False
            self.arena_question_ask_string = "Multiple users can win $points $currency by answering: $index) In $game, $question"
            self.arena_question_reward_string = "The following users answered the question correctly and won $points $currency: $users"

            #Trivia Rewards
            self.enable_loyalty_point_rewards = True
            self.default_loyalty_point_value = 10
            self.percent_loyalty_point_value_increase_on_unanswered = 0
            self.percent_loyalty_point_value_decrease_on_answered = 0

            #Output Settings
            self.create_current_question_file = False
            self.debug_level = "Warn"
            #self.enable_chat_errors = False
            #self.enable_chat_syntax_hints = True
            self.enable_chat_command_confirmations = True
            self.enable_file_logging = False
            


    def Reload(self, jsondata):
        self.__dict__ = json.loads(jsondata, encoding="utf-8")
        return

    def Save(self, settings_file):
        try:
            with codecs.open(settings_file, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8")
        except IOError as e:
            Log("Settings Save: Failed to save settings to the file: " + str(e), DebugLevel.Fatal)
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

class DebugLevel(Enum):
    All = 1
    Debug = 2
    Info = 3
    Warn = 4
    Fatal = 5

#---------------------------------------
# Functions
#---------------------------------------
#   [Required] Initialize Data (Only called on load)
def Init():
    global script_settings
    script_settings = Settings(settings_file)
    script_settings.Save(settings_file)
    script_settings.duration_between_questions = max(script_settings.duration_between_questions, 0)
    script_settings.duration_of_questions = max(script_settings.duration_of_questions, 0)
    LoadTrivia()
    Log("Init: Trivia Minigame Loaded", DebugLevel.Info)
    return

#Function that runs every time the Trivia command is used
def Execute(data):
    global active
    global current_question_index

    #Algorithm to start trivia if the trivia has been paused. Requires admin permission.
    if not active:
        if Parent.HasPermission(data.User, script_settings.permissions_admins, "") and data.Message == "!trivia start":
            active = True
            Log("Trivia Start: Minigame Started with Command", DebugLevel.Debug)
            if script_settings.enable_chat_command_confirmations: Post("Trivia Minigame Started.")

    #If (the streamer is live OR trivia can run when offline) and trivia is active...
    if (Parent.IsLive() or not script_settings.run_only_when_live) and active and data.IsChatMessage():
        #Check if the chatter has administrator permissions. If so, see if they are running an admin command.
        if str(data.Message).startswith("!trivia") and Parent.HasPermission(data.User, script_settings.permissions_admins, "") and data.GetParamCount() > 0:
            subcommand = data.GetParam(1)
            if subcommand == "stop":
                active = False
                Log("Trivia Stop: Minigame Stopped with Command", DebugLevel.Debug)
                if script_settings.enable_chat_command_confirmations: 
                    Post("Trivia Minigame Stopped.")

            elif subcommand == "count":
                Post("Number of questions available: " + str(len(questions_list)))

            elif subcommand == "answers":
                if current_question_index == -1:
                    Post("No questions are currently loaded.")
                else:
                    Post("Answers to the current question: " + ", ".join(questions_list[current_question_index].get_answers()))

            elif subcommand == "save":
                SaveTrivia()
                if script_settings.enable_chat_command_confirmations: 
                    Post("Trivia save: Saved.")

            elif subcommand == "load":
                if data.GetParamCount() == 2 and len(questions_list) > 0:
                    NextQuestion()
                    #No confirmation necessary - if a question is loaded successfully the result will be obvious
                elif data.GetParamCount() == 3:
                    try:
                        question_index = int(data.GetParam(2)) - 1
                        if question_index < 0 or question_index > len(questions_list) - 1:
                            raise IndexError("Question index out of bounds.")
                        NextQuestion(question_index)
                    except (ValueError, IndexError) as e:
                        Log("Trivia Load: Question could not be loaded: " + str(e), DebugLevel.Warn)
                        Post("Error loading question. Was the supplied index a number and between 1 and " + str(len(questions_list)) + "?")
                else:
                    Log("Trivia Load: Subcommand used, but no questions exist that can be loaded.", DebugLevel.Info)
                    Post("Cannot load questions - no questions exist.")

            elif subcommand == "add":
                if data.GetParamCount() == 2:
                    Post("Syntax: '!trivia add game:[game name], question:[trivia question], answers:[comma-separated list of answers]")
                else:
                    #Get all of the required attributes from the message
                    #Try/catch to make sure points was convertible to an int
                    try:
                        new_points = int(GetAttribute("points", data.Message))
                    except ValueError:
                        new_points = script_settings.default_loyalty_point_value
                    try:
                        new_game = GetAttribute("game", data.Message)
                    except ValueError:
                        #If the attribute is not found, display an error
                        Log("Trivia Add: Question not added. No game attribute detected in command call.", DebugLevel.Warn)
                        Post("Error: No game attribute detected. Please supply a game name.")
                        return

                    try:
                        new_question_text = GetAttribute("question", data.Message)
                    except ValueError:
                        #If the attribute is not found, display an error
                        Log("Trivia Add: Question not added. No question attribute detected in command call.", DebugLevel.Warn)
                        Post("Error: No question attribute detected.")
                        return

                    try:
                        new_answers = GetAttribute("answers", data.Message).split(",")
                    except ValueError:
                        #If the attribute is not found, display an error
                        Log("Trivia Add: Question not added. No answers attribute detected in command call.", DebugLevel.Warn)
                        Post("Error: No answers attribute detected. A question cannot be added without valid answers.")
                        return

                    #strip all whitespace from the beginning and ends of the answers
                    i = 0
                    while i < len(new_answers):
                        new_answers[i] = new_answers[i].strip()
                        i = i + 1
                        
                    #create the Question object and add it to the list of questions, then save the new list of questions
                    global questions_list
                    new_question = Question(game=new_game, points=new_points, question=new_question_text, answers=new_answers)
                    questions_list.append(new_question)
                    if SaveTrivia():
                        Log("Trivia Add: A new question has been added.", DebugLevel.Info)
                        Post("Question added.")
            
            elif subcommand == "remove":
                if data.GetParamCount() == 2:
                    Post("Syntax: '!trivia remove [Question Index]")
                else:
                    try:
                        question_index = int(data.GetParam(2)) - 1
                        questions_list.pop(question_index)
                        if question_index == current_question_index:
                            current_question_index = -1
                        if script_settings.enable_chat_command_confirmations: Post("Question removed.")
                    except (ValueError, IndexError) as e:
                        Log("Trivia Remove: Question could not be removed: " + str(e), DebugLevel.Warn)
                        Post("Error removing question. Was the supplied index a number and between 1 and " + str(len(questions_list)) + "?")

            elif subcommand == "modify":
                if data.GetParamCount() == 2:
                    Post("Syntax: !trivia modify [Integer Question Index] (game:[New Value]), (question:[New Value]), (points:[New Value]) (answers [add/remove/set]: [New Value], [New Value], ...)")
                else:
                    #Parameter two indicates the index of the question
                    try:
                        question_index = int(data.GetParam(2)) - 1
                    except ValueError:
                        #If parameter three was not an integer, display an error message
                        Log("Trivia Modify: Trivia Modify subcommand supplied a non-integer question index.", DebugLevel.Warn)
                        Post("Error: The supplied index was not a number.")
                        return

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
                        questions_list[question_index].set_game(newGame)
                        changes = True
                    if newQuestion:
                        questions_list[question_index].set_question(newQuestion)
                        changes = True
                    if newPoints:
                        try:
                            questions_list[question_index].set_points(int(newPoints))
                            changes = True
                        except ValueError as e:
                            Log("Trivia Modify: Trivia Modify subcommand supplied a non-integer point value.", DebugLevel.Warn)
                            Post("Error: The supplied point value was not a number. The question's point value was not changed.")
                    if newAnswerSet:
                        questions_list[question_index].set_answers(newAnswerSet)
                        changes = True
                    else:
                        current_answers = questions_list[question_index].get_answers()
                        if newAnswers:
                            for answer in newAnswers:
                                if answer not in current_answers:
                                    current_answers.append(answer)
                                    current_answers.sort()
                                    changes = True
                        if oldAnswers:  
                            for answer in oldAnswers:
                                if answer in current_answers:
                                    current_answers.remove(answer)
                                    changes = True
                    
                    if changes:
                        if SaveTrivia():
                            Post("Question modified.")
        elif str(data.Message).startswith("!trivia") and not Parent.HasPermission(data.User, script_settings.permissions_admins, "") and data.GetParamCount() > 0:
            Log(data.UserName + " attempted to use trivia admin commands without permission. " + str(data.Message), DebugLevel.Info)
            Post(data.UserName + ", you do not have the permissions to use this command.")
        if Parent.HasPermission(data.User, script_settings.permissions_players, ""):
            if str(data.Message).startswith("!trivia"):
                if current_question_index == -1:
                    if (not script_settings.automatically_run_next_question) and ready_for_next_question:
                        NextQuestion()
                    else:
                        global question_start_time
                        Log("Trivia: There is no trivia question active.", DebugLevel.Info)
                        Post("There are no active trivia questions. The next trivia question arrives in " + str(datetime.fromtimestamp(question_start_time - time.time()).strftime('%M minutes and %S seconds.')))
                else:
                    Post(str(current_question_index + 1) + ") " + questions_list[current_question_index].as_string() + " Time remaining: " + str(datetime.fromtimestamp(question_start_time - time.time()).strftime('%M minutes and %S seconds.')))
            elif current_question_index != -1:
                CheckForMatch(data)
            
#Function that runs continuously
def Tick():
    global question_start_time
    global next_question_file_update_time
    global active
    if active and (not script_settings.run_only_when_live or (script_settings.run_only_when_live and Parent.IsLive())):
        # If time has expired, check to see if there is a current question
        # If there is a current question, depending on settings the answers may need to be displayed and the points adjusted
        current_time = time.time()
        if not current_question_index == -1:
            if current_time > question_expiry_time:
                global current_question_index
                Log("Tick: Question time exceeded. Ending question.", DebugLevel.Debug)
                EndQuestion()     
        else:
            if current_time > question_start_time:
                if script_settings.automatically_run_next_question:
                    NextQuestion()
                else:
                    global ready_for_next_question
                    ready_for_next_question = True
        #Log("Current time: " + str(current_time) + ". Update time: " + str(next_question_file_update_time))
        if current_time > next_question_file_update_time:
            #Log("Tick: Updating Question File. Current time: " + str(current_time) + " vs " + str(next_question_file_update_time), DebugLevel.Debug)
            UpdateCurrentQuestionFile()
    return

def CheckForMatch(data):
    global current_question_index
    try:
        current_question = questions_list[current_question_index]
        current_answers = current_question.get_answers()
        for answer in current_answers:
            if data.Message.lower() == answer.lower():
                correct_users_dict[data.User] = data.UserName
                Log("CheckForMatch: Match detected between answer " + answer + " and message " + data.Message + ". User " + data.UserName + " added to the list of correct users.", DebugLevel.Debug)
                if not script_settings.enable_arena_mode:
                    Log("CheckForMatch: Arena mode is not active. Ending question.", DebugLevel.Debug)
                    EndQuestion()
                    return
            else:
                Log("CheckForMatch: No match detected between answer " + answer + " and message \"" + data.Message + "\".", DebugLevel.Debug)
        Log("CheckForMatch: No match detected in the message from user " + data.UserName + ".", DebugLevel.Debug)                  
        return False
    except IndexError:
        current_question_index = -1
        return False

def EndQuestion():
    global current_question_index
    if not current_question_index == -1:
        #Question is ending. Reward users, if desired
        if len(correct_users_dict) > 0:
            Log("EndQuestion: Winners detected. Distributing points.", DebugLevel.Debug)
            #Get the number of points being rewarded
            points_being_rewarded = 0
            if script_settings.enable_loyalty_point_rewards:
                points_being_rewarded = questions_list[current_question_index].get_points()
                Log("EndQuestion: Base points rewarded by question: " + str(points_being_rewarded) + ".", DebugLevel.Debug)
                if script_settings.enable_arena_points_dividing:
                    points_being_rewarded = points_being_rewarded / len(correct_users_dict)
                    Log("EndQuestion: Divided points rewarded by question: " + str(points_being_rewarded) + ".", DebugLevel.Debug)

            #Iterate through the correct users dictionary
            correct_usernames = []
            for user_ID in correct_users_dict.keys():
                if script_settings.enable_loyalty_point_rewards:
                    Parent.AddPoints(user_ID, correct_users_dict[user_ID], points_being_rewarded)
                    Log("EndQuestion: Adding " + str(questions_list[current_question_index].get_points()) + " " + Parent.GetCurrencyName() + " to user " + correct_users_dict[user_ID] + ".", DebugLevel.Debug)
                Log("EndQuestion: Adding user ID " + str(user_ID) + " to the list of correct users with the username " + correct_users_dict[user_ID] + ".", DebugLevel.Debug)
                correct_usernames.append(correct_users_dict[user_ID])
            correct_usernames.sort()
            Log("EndQuestion: Final correct users list for this reward: " + str(correct_usernames), DebugLevel.Debug)

            #Reduce the reward for that question, if desired
            if script_settings.percent_loyalty_point_value_decrease_on_answered > 0:
                question_points = questions_list[current_question_index].get_points()
                new_points = int(question_points - (question_points * (script_settings.percent_loyalty_point_value_decrease_on_answered / 100.0)))
                questions_list[current_question_index].set_points(new_points)
                Log("EndQuestion: Reducing points for question at index " + str(current_question_index + 1) + " by " + 
                    str(script_settings.percent_loyalty_point_value_decrease_on_answered) + " percent. (" + str(question_points) + " - " + 
                    str(int(question_points * (script_settings.percent_loyalty_point_value_decrease_on_answered / 100.0))) + " = " + str(new_points) + ")", DebugLevel.Debug)
                SaveTrivia()

            #Post message rewarding users
            if script_settings.enable_arena_mode:
                if script_settings.create_current_question_file:
                    global next_question_file_update_time
                    UpdateCurrentQuestionFile(ParseString(string = script_settings.arena_question_reward_string, points = points_being_rewarded, users = correct_usernames))
                    next_question_file_update_time = time.time() + 10
                else:
                    Post(ParseString(string = script_settings.arena_question_reward_string, points = points_being_rewarded, users = correct_usernames))
            else:
                if script_settings.create_current_question_file:
                    global next_question_file_update_time
                    global question_start_time
                    UpdateCurrentQuestionFile(ParseString(string = script_settings.standard_question_reward_string, points = points_being_rewarded, users = correct_usernames))
                    next_question_file_update_time = time.time() + 10
                else:
                    Post(ParseString(string = script_settings.standard_question_reward_string, points = points_being_rewarded, users = correct_usernames))
        else:
            Log("EndQuestion: No winners detected.", DebugLevel.Debug)
            if script_settings.show_answers_if_no_winners:
                Log("EndQuestion: Setting to show answers enabled. Answers are [" + ",".join(questions_list[current_question_index].get_answers()) + "].", DebugLevel.Debug)
                if script_settings.create_current_question_file:
                    global next_question_file_update_time
                    global question_start_time
                    UpdateCurrentQuestionFile(ParseString(string = script_settings.no_winners_response_string))
                    next_question_file_update_time = time.time() + 10
                else:
                    Post(ParseString(string = script_settings.no_winners_response_string))
            if int(script_settings.percent_loyalty_point_value_increase_on_unanswered) > 0:
                question_points = questions_list[current_question_index].get_points()
                new_points = int(question_points + question_points * (script_settings.percent_loyalty_point_value_increase_on_unanswered / 100.0))
                questions_list[current_question_index].set_points(new_points)
                Log("EndQuestion: Increasing points for question at index " + str(current_question_index + 1) + " by " + 
                    str(script_settings.percent_loyalty_point_value_increase_on_unanswered) + " percent. (" + str(question_points) + " + " + 
                    str(int(question_points * (script_settings.percent_loyalty_point_value_increase_on_unanswered / 100.0))) + " = " + str(new_points) + ")", DebugLevel.Debug)
                SaveTrivia()
    current_question_index = -1
    global question_start_time
    global ready_for_next_question
    question_start_time = time.time() + (script_settings.duration_between_questions * 60)
    ready_for_next_question = False

def NextQuestion(question_index = -1):
    Log("NextQuestion: Called with index of " + str(question_index) + ".", DebugLevel.Debug)
    global current_question_index
    global question_expiry_time
    global ready_for_next_question
    previous_question_index = -1
    previous_question_index = current_question_index  #Log the previous question to prevent duplicates 
    #Start up a new question, avoiding using the same question twice in a row
    if question_index == -1:
        if previous_question_index != -1 and len(questions_list) > 1:
            while True:
                current_question_index = Parent.GetRandom(0,len(questions_list))
                if current_question_index != previous_question_index: 
                    break
        else: 
            current_question_index = Parent.GetRandom(0,len(questions_list))
    else:
        current_question_index = question_index
    Log("NextQuestion: Loaded question at Index " + str(current_question_index + 1) + ".", DebugLevel.Debug)
    if not script_settings.create_current_question_file:
        if script_settings.enable_arena_mode:
            Post(ParseString("Multiple users can win $points $currency by answering: $index) In $game, $question"))
        else:
            Post(ParseString("For $points $currency: $index) In $game, $question"))
    question_expiry_time = time.time() + ((script_settings.duration_of_questions) * 60)
    Log("NextQuestion: Next Question at " + datetime.fromtimestamp(question_expiry_time).strftime('%H:%M:%S') + ".", DebugLevel.Debug)
    ready_for_next_question = False
    UpdateCurrentQuestionFile()

def GetAttribute(attribute, message):
    Log("GetAttribute: Called with message \"" + message + "\" looking for attribute \"" + attribute + "\".", DebugLevel.Debug)
    attribute = attribute.lower() + ":"
    #The start index of the attribute begins at the end of the attribute designator, such as "game:"
    try:
        index_of_beginning_of_attribute = message.lower().index(attribute) + len(attribute)
        Log("GetAttribute: Attribute found at index " + str(index_of_beginning_of_attribute), DebugLevel.Debug)
    except ValueError as e:
        Log("GetAttribute: The attribute was not found in the message.", DebugLevel.Debug)
        if attribute.lower() == "points=":
            Log("GetAttribute: Default points are being applied.", DebugLevel.Debug)
            return script_settings.default_loyalty_point_value
        raise e
    #The end index of the attribute is at the last space before the next attribute designator, or at the end of the message
    try:
        index_of_end_of_attribute = message[index_of_beginning_of_attribute:index_of_beginning_of_attribute + message[index_of_beginning_of_attribute:].index(":")].rindex(",")
    except ValueError:
        #If this error is thrown, the end of the message was hit, so just return all of the remaining message
        return message[index_of_beginning_of_attribute:].strip()
    result = message[index_of_beginning_of_attribute:index_of_beginning_of_attribute + index_of_end_of_attribute].strip().strip(",")
    Log("GetAttribute: " + attribute + " successfully retrieved with a value of \"" + result + "\".", DebugLevel.Debug)
    return result

def ParseString(string, points = -1, users = []):
    #Apply question attributes to a string
    global current_question_index
    if points == -1:
        points = questions_list[current_question_index].get_points()
    string = string.replace("$index", str(current_question_index + 1))
    string = string.replace("$currency", str(Parent.GetCurrencyName()))
    string = string.replace("$question", questions_list[current_question_index].get_question())
    string = string.replace("$points", str(points))
    string = string.replace("$answers", ",".join(questions_list[current_question_index].get_answers()))
    string = string.replace("$game", questions_list[current_question_index].get_game())
    string = string.replace("$users", ",".join(users))
    string = string.replace("$time", str(script_settings.duration_of_questions))
    Log("ParseString: Result of string parsing: \"" + string + "\"", DebugLevel.Debug)
    return string

def SaveTrivia():
    try:        
        #if the trivia file does not exist, create it
        if not os.path.exists(questions_file):
            with io.open(questions_file, 'w') as outfile:
                outfile.write(json.dumps({}))
            Log("SaveTrivia: The trivia file was not found. A new one was created.", DebugLevel.Info)

        #record the questions
        with open (questions_file, 'w') as outfile:
            outfile.seek(0)
            #When writing the Questions to disk, use the Question.toJSON() function
            json.dump(questions_list, outfile, indent=4, default=lambda q: q.toJSON())
            outfile.truncate()
            Log("SaveTrivia: The trivia file was successfully updated.", DebugLevel.Debug)
        
        return True

    except IOError as e:
        Log("SaveTrivia: Unable to save trivia questions: " + str(e), DebugLevel.Fatal)
        raise e

def LoadTrivia():
    #Ensure the questions file exists
    if os.path.exists(questions_file):
        try:
            with io.open(questions_file) as infile:
                objectdata = json.load(infile)    #Load the json data

            #For each object/question in the objectdata, create new questions and feed them to the questions_list
            for question in objectdata:
                new_question = Question(game=question["Game"], points=question["Points"], question=question["Question"], answers=question["Answers"])
                questions_list.append(new_question)
            Log("LoadTrivia: Questions loaded: " + str(len(questions_list)), DebugLevel.Debug)
        except ValueError:
            Log("LoadTrivia: Question file exists, but contains no data.", DebugLevel.Warn)
    else:
        Log("LoadTrivia: No questions file exists.", DebugLevel.Warn)

#Reload Settings (Called when a user clicks the Save Settings button in the Chatbot UI)
def ReloadSettings(jsonData):
    # Execute json reloading here
    Log("ReloadSettings: Saving settings.", DebugLevel.Debug)
    global script_settings
    script_settings.__dict__ = json.loads(jsonData)
    script_settings.Save(settings_file)
    Log("ReloadSettings: Settings saved and applied successfully", DebugLevel.Debug)
    return

def Log(message, level = DebugLevel.All):
    if script_settings.enable_file_logging:
        global log_file
        file = open(log_file, "a+")
        file.writelines(str(datetime.now()).ljust(26) + " " + str(level.name + ":").ljust(10) + message + "\n")
        file.close()
    if script_settings.debug_level >= level.value:
        Parent.Log(ScriptName, message)

def Post(message):
    Parent.SendStreamMessage(message)

def UpdateCurrentQuestionFile(line = None, duration = 1):
    if script_settings.create_current_question_file:
        global current_question_file
        global next_question_file_update_time
        file = open(current_question_file, "w+")
        file.seek(0)
        if line:
            Log("UpdateCurrentQuestionFile: Line supplied to method. Writing line to file.", DebugLevel.Debug)
            file.write(line + "                             ")
        elif (not ready_for_next_question or script_settings.automatically_run_next_question) and current_question_index == -1:
            #Display Countdown
            file.write("Time until next question: " + str(datetime.fromtimestamp(question_start_time - time.time()).strftime('%M:%S')) + ".                         ")
        elif ready_for_next_question and current_question_index == -1 and not script_settings.automatically_run_next_question:
            #Display ready message
            file.write("Next question ready. Type !trivia to begin!                             ")
        elif not current_question_index == -1:
            #Display current question
            if script_settings.enable_arena_mode:
                file.write(ParseString(str(datetime.fromtimestamp(question_expiry_time - time.time()).strftime('%M:%S')) + ") In $game, $question                          "))
            else:
                file.write(ParseString(str(datetime.fromtimestamp(question_expiry_time - time.time()).strftime('%M:%S')) + ") In $game, $question                          "))
        file.truncate()
        file.close()
        next_question_file_update_time = time.time() + duration