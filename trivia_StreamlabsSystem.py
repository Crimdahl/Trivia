#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
#---------------------------------------
# Libraries and references
#---------------------------------------
import sys
import os
import io
import json
import random
import codecs
import time

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
questions_list = []
current_question_index = -1
reset_time = 0
active = True

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
            self.RunOnlyWhenLive = True
            self.PlayPermission = "Everyone"
            self.AdminPermission = "Moderator"

            #Trivia Questions
            self.QuestionDelayInMinutes = 10
            self.QuestionString = "Win $points $currency by answering: $index) In $game, $question"
            self.QuestionSuccessResponse = "$user has answered correctly and won $points $currency."
            self.ShowAnswersOnFailure = False
            self.QuestionFailureResponse = "Nobody answered the previous question. The answers were: $answers."

            #Trivia Rewards
            self.QuestionsRewardLoyaltyPoints = True
            self.QuestionDefaultPointValue = 50
            self.RewardDecreaseOnAnswer = 10
            self.RewardIncreaseOnNoAnswer = 10

            #Responses
            self.EnableDebug = True
            self.EnableChatErrors = False
            self.EnableChatSyntaxHints = True
            self.EnableChatConfirmations = True
            


    def Reload(self, jsondata):
        self.__dict__ = json.loads(jsondata, encoding="utf-8")
        return

    def Save(self, settings_file):
        try:
            with codecs.open(settings_file, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8")
        except:
            Log("Failed to save settings to the file. Fix error and try again.")
        return

class Question(object):
    # Object-specific Variables
    points = None
    game = None
    question = None
    answers = []

    def __init__(self, **kwargs):
        self.points = kwargs["points"] if "points" in kwargs else ScriptSettings.QuestionDefaultPointValue
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

#---------------------------------------
# Functions
#---------------------------------------
#   [Required] Initialize Data (Only called on load)
def Init():
    global ScriptSettings
    global reset_time
    ScriptSettings = Settings(settings_file)
    ScriptSettings.Save(settings_file)
    LoadTrivia()
    reset_time = time.time() + (ScriptSettings.QuestionDelayInMinutes * 60)
    if ScriptSettings.EnableDebug: Log("Trivia Minigame Loaded")
    if ScriptSettings.EnableChatConfirmations: Post("Trivia Minigame Loaded.")
    return

#Function that runs every time the Trivia command is used
def Execute(data):
    global active
    global current_question_index

    if not active:
        if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, "") and data.Message == "!trivia start":
            active = True
            if ScriptSettings.EnableDebug: Log("Trivia Minigame Started with Command")
            if ScriptSettings.EnableChatConfirmations: Post("Trivia Minigame Started.")
    if active and Parent.HasPermission(data.User, ScriptSettings.PlayPermission, "") and (not ScriptSettings.RunOnlyWhenLive or (ScriptSettings.RunOnlyWhenLive and Parent.IsLive())):
        #If the first thing in chat was '!trivia"
        if str.startswith(data.Message,"!trivia"):
            number_of_params = data.GetParamCount()     #The number of parameters from a chat message

            #Display command usage information if no other arguments are supplied
            if number_of_params == 1:
                if current_question_index != -1:
                    if ScriptSettings.EnableDebug: Log("INFO: There is no trivia question active.")
                    if ScriptSettings.EnableChatErrors: Post("There is no trivia question active.")
                else:
                    Post(str(current_question_index + 1) + ") " + questions_list[current_question_index].as_string())
            #If there were additional arguments, get the sub argument
            else:
                #Look for subcommands
                command = data.GetParam(1)
                if command == "stop":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        active = False
                        if ScriptSettings.EnableDebug: Log("Trivia Minigame Stopped with Command")
                        if ScriptSettings.EnableChatConfirmations: Post("Trivia Minigame Stopped.")
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the stop subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                #-----------
                #LOAD: Immediately load another trivia question, bypassing question cooldowns
                #-----------   
                elif command == "load":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        #If the syntax is correct, load a new question
                        if len(questions_list) > 0:
                            DisplayNewQuestion()
                            global reset_time
                            reset_time = time.time() + (ScriptSettings.QuestionDelayInMinutes * 60)
                        else:
                            if ScriptSettings.EnableDebug: Log("ERROR: No questions exist that can be loaded.")
                            if ScriptSettings.EnableChatErrors: Post("No questions exist that can be loaded.")
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the load subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                #-----------
                #ADD: Add a new question
                #-----------   
                elif command == "add":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        if number_of_params == 2:
                            if ScriptSettings.EnableChatSyntaxHints: Post("Syntax: '!trivia add game:[game name] question:[trivia question] answers:[comma-separated list of answers] (points:[optional default point value])")
                        else:
                            #Make a string out of the whole message
                            whole_message = str(data.Message)

                            #Get all of the required attributes from the message
                            #Try/catch to make sure points was convertible to an int
                            try:
                                new_points = int(GetAttribute("points", whole_message))
                            except ValueError:
                                if ScriptSettings.EnableDebug: Log("ERROR: A NaN points value was supplied.")
                                if ScriptSettings.EnableChatErrors: Post("Error: The points value supplied was not a number.")
                                return

                            try:
                                new_game = GetAttribute("game", whole_message)
                            except ValueError:
                                #If the attribute is not found, display an error
                                if ScriptSettings.EnableDebug: Log("ERROR: question not added. No game attribute detected in command call.")
                                if ScriptSettings.EnableChatErrors: Post("Error: No game detected.")
                                return

                            try:
                                new_question_text = GetAttribute("question", whole_message)
                            except ValueError:
                                #If the attribute is not found, display an error
                                if ScriptSettings.EnableDebug: Log("ERROR: question not added. No question attribute detected in command call.")
                                if ScriptSettings.EnableChatErrors: Post("Error: No question detected.")
                                return

                            try:
                                new_answers = GetAttribute("answers", whole_message).split(",")
                            except ValueError:
                                #If the attribute is not found, display an error
                                if ScriptSettings.EnableDebug: Log("ERROR: question not added. No answers attribute detected in command call.")
                                if ScriptSettings.EnableChatErrors: Post("Error: No answers detected.")
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
                            if ScriptSettings.EnableDebug: Log("INFO: A new question has been added.")
                            if ScriptSettings.EnableChatConfirmations: Post("Question added.")
                            SaveTrivia()
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the add subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                #-----------
                #REMOVE: Remove a question
                #-----------   
                elif command == "remove":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        #TODO: Code function to remove the question at the most recent question index. Should take a numeric argument to specify a question index to remove.
                        pass
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the remove subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                #-----------
                #MODIFY: Modify a question
                #----------- 
                elif command == "modify":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        modify_usage_string = "Command usage: '!trivia modify [Integer Question Index] [game/question/points/answers (add/remove/set)] [New Value]'"
                        #Check to make sure the number of parameters would be enough to properly run this question
                        if number_of_params >= 5:
                            #Parameter three indicates the index of the question
                            try:
                                question_index = int(data.GetParam(2)) - 1
                            except ValueError:
                                #If parameter three was not an integer, display an error message
                                if ScriptSettings.EnableDebug: Log("ERROR: Trivia Modify subcommand supplied a non-integer question index.")
                                if ScriptSettings.EnableChatSyntaxHints: Post(modify_usage_string)
                                return

                            #Before we modify, make sure the question at the supplied index exists
                            try:
                                current_question = questions_list[question_index]
                            except IndexError:
                                #If parameter three was not an integer, display an error message
                                if ScriptSettings.EnableDebug: Log("ERROR: Trivia Modify subcommand supplied a question index that does not exist.")
                                if ScriptSettings.EnableChatErrors: Post("ERROR: No question exists at the supplied index.")
                                return

                            #Parameter four indicates the type of modification to perform to the question
                            command = data.GetParam(3)

                            #Get everything after Param 4, stripping off whitespace
                            whole_message = str(data.Message)
                            argument = whole_message[whole_message.index(command) + len(command):].strip()

                            #Switch based on Param 4
                            if command == "game":
                                #Change the game attribute of the question, then save.
                                current_question.set_game(argument)
                                SaveTrivia()
                                if ScriptSettings.EnableDebug: Log("INFO: Trivia question at index " + str(question_index) + " has been successfully modified: 'game' attribute changed to " + argument + ".")
                                if ScriptSettings.EnableChatConfirmations: Post("Game modified.")
                            elif command == "question":
                                #Change the question attribute of the question, then save.
                                current_question.set_question(argument)
                                SaveTrivia()
                                if ScriptSettings.EnableDebug: Log("INFO: Trivia question at index " + str(question_index) + " has been successfully modified: 'question' attribute changed to " + argument + ".")
                                if ScriptSettings.EnableChatConfirmations: Post("Question modified.")
                            elif command == "points":
                                #Try/catch block in case the argument supplied was not a number
                                try:
                                    #Change the points attribute of the current or previous question, then save.
                                    current_question.set_points(int(argument))
                                    SaveTrivia()
                                    if ScriptSettings.EnableDebug: Log("INFO: Trivia question at index " + str(question_index) + " has been successfully modified: 'points' attribute changed to " + argument + ".")
                                    if ScriptSettings.EnableChatConfirmations: Post("Points modified.")
                                except ValueError:
                                    if ScriptSettings.EnableDebug: Log("ERROR: Trivia question at index " + str(question_index) + " was not successfully modified: NaN Point Value Supplied.")
                                    if ScriptSettings.EnableChatErrors: Post("Error: The supplied point value was not a number.")
                            elif command == "answers":
                                #Get the next parameter to see how we're modifying the answers
                                command = data.GetParam(4)
                                argument = whole_message[whole_message.index(command) + len(command):].strip()

                                if command == "set":
                                    #Change entire answer set to the arguments provided
                                    success = current_question.set_answers([answer.strip() for answer in argument.split(",")])
                                    if success:
                                        if ScriptSettings.EnableDebug: Log("INFO: Trivia question at index " + str(question_index) + " has been successfully modified: 'answers' set: " + argument + ".")
                                        if ScriptSettings.EnableChatConfirmations: Post("Answers set.")
                                        SaveTrivia()
                                    else:
                                        if ScriptSettings.EnableDebug: Log("ERROR: Failed to set the answers for the question at that index.")
                                        if ScriptSettings.EnableChatErrors: Post("Error: Failed to set the answers for the question at that index.")
                                elif command == "add":
                                    #Add the supplied argument to the list of acceptable answers
                                    success = current_question.add_answer(argument)
                                    if success:
                                        if ScriptSettings.EnableDebug: Log("INFO: Trivia question at index " + str(question_index) + " has been successfully modified: 'answers' added: " + argument + ".")
                                        if ScriptSettings.EnableChatConfirmations: Post("Answer added.")
                                        SaveTrivia()
                                    else:
                                        if ScriptSettings.EnableDebug: Log("ERROR: Trivia question at index " + str(question_index) + " already had the supplied answer.")
                                        if ScriptSettings.EnableChatErrors: Post("Error: The question at the index supplied already had that valid answer.")
                                elif command == "remove":
                                    #Remove the supplied argument from the list of acceptable answers
                                    success = current_question.remove_answer(argument)
                                    if success:
                                        if ScriptSettings.EnableDebug: Log("INFO: Trivia question at index " + str(question_index) + " has been successfully modified: 'answers' removed: " + argument + ".")
                                        if ScriptSettings.EnableChatConfirmations: Post("Answer removed.")
                                        SaveTrivia()
                                    else:
                                        if ScriptSettings.EnableDebug: Log("ERROR: Trivia question at index " + str(question_index) + " did not have the supplied answer.")
                                        if ScriptSettings.EnableChatErrors: Post("Error: Answer " + argument + " does not exist for the question at the index supplied.")
                                else:
                                    #The subcommand was invalid. Display usage information.
                                    if ScriptSettings.EnableDebug: Log("ERROR: Trivia Modify Answer subcommand supplied an invalid argument.")
                                    if ScriptSettings.EnableChatSyntaxHints: Post(modify_usage_string)                
                        #There were not enough parameters supplied: display an error message
                        else:
                            if ScriptSettings.EnableDebug: Log("ERROR: Trivia Modify subcommand called with incorrect arguments.")
                            if ScriptSettings.EnableChatSyntaxHints: Post(modify_usage_string)
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the modify subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                elif command == "count":
                    Post("Number of questions available: " + str(len(questions_list)))
                    return
                elif command == "answers":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        if current_question_index == -1:
                            if ScriptSettings.EnableChatErrors: Post("No questions are currently loaded.")
                        else:
                            Post("Answers to the current question: " + ", ".join(questions_list[current_question_index].get_answers()))
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the answers subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                elif command == "save":
                    if Parent.HasPermission(data.User, ScriptSettings.AdminPermission, ""):
                        SaveTrivia()
                    else:
                        if ScriptSettings.EnableDebug: Log(data.UserName + " attempted to use the save subcommand without permission.")
                        if ScriptSettings.EnableChatErrors: Post(data.UserName + ", you do not have the permissions to use this command.")
                elif command == "help":
                    if number_of_params == 2:
                        if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with no arguments.")
                        Post("Available subcommands: load, add, remove, modify, count, answers, save.")
                    else: 
                        command = data.GetParam(3)
                        if command == "load":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'load' argument.")
                            Post("Load immediately starts a new random question.")
                        elif command == "add":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'add' argument.")
                            Post("Add allows for the addition of new questions.")
                        elif command == "remove":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'remove' argument.")
                            Post("Remove allows for the removal of questions.")
                        elif command == "modify":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'modify' argument.")
                            Post("Modify allows for the modification of existing questions.")
                        elif command == "count":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'count' argument.")
                            Post("Count displays the total number of questions available. Takes no arguments.")
                        elif command == "answers":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'answers' argument.")
                            Post("Answers displays the list of correct answers for the current question.")
                        elif command == "save":
                            if ScriptSettings.EnableDebug: Log("INFO: Trivia help subcommand called with 'save' argument.")
                            Post("Save manually saves question information to the JSON file.")

        else:
            if data.IsChatMessage() and current_question_index != -1 and CheckForMatch(data): 
                #Display success message
                Post(ParseString(ScriptSettings.QuestionSuccessResponse, data))

                if ScriptSettings.QuestionsRewardLoyaltyPoints: 
                    #Add points to user
                    if ScriptSettings.EnableDebug: Log("INFO: Adding " + str(questions_list[current_question_index].get_points()) + " " + Parent.GetCurrencyName() + " to user " + data.UserName + ".")
                    Parent.AddPoints(data.User, data.UserName, questions_list[current_question_index].get_points())

                #Adjust points if necessary
                if ScriptSettings.RewardDecreaseOnAnswer > 0:
                    question_points = questions_list[current_question_index].get_points()
                    new_points = int(question_points - (question_points * (ScriptSettings.RewardDecreaseOnAnswer / 100.0)))
                    questions_list[current_question_index].set_points(new_points)
                    if ScriptSettings.EnableDebug: Log("Reducing points for question at index " + str(current_question_index + 1) + " by " + str(ScriptSettings.RewardDecreaseOnAnswer) + " percent. (" + str(question_points) + " - " + str(int(question_points * (ScriptSettings.RewardDecreaseOnAnswer / 100.0))) + " = " + str(new_points) + ")")
                    SaveTrivia()

                #Set current question index to nothing
                current_question_index = -1
            

#Function that runs continuously
def Tick():
    global reset_time
    global active
    if active and (not ScriptSettings.RunOnlyWhenLive or (ScriptSettings.RunOnlyWhenLive and Parent.IsLive())):
        # If time has expired, check to see if there is a current question
        # If there is a current question, depending on settings the answers may need to be displayed and the points adjusted
        if time.time() > reset_time:
            DisplayNewQuestion()
            reset_time = time.time() + (ScriptSettings.QuestionDelayInMinutes * 60)
    return

def DisplayNewQuestion():
    previous_question_index = -1
    previous_question_index = current_question_index  #Log the previous question to prevent duplicates
    if current_question_index != -1:
        if ScriptSettings.ShowAnswersOnFailure:
            Post(ParseString(ScriptSettings.QuestionFailureResponse))
        if int(ScriptSettings.RewardIncreaseOnNoAnswer) > 0:
            question_points = questions_list[current_question_index].get_points()
            new_points = int(question_points + question_points * (ScriptSettings.RewardDecreaseOnAnswer / 100.0))
            questions_list[current_question_index].set_points(new_points)
            if ScriptSettings.EnableDebug: Log("Increasing points for question at index " + str(current_question_index + 1) + " by " + str(ScriptSettings.RewardDecreaseOnAnswer) + " percent. (" + str(question_points) + " + " + str(int(question_points * (ScriptSettings.RewardDecreaseOnAnswer / 100.0))) + " = " + str(new_points) + ")")
            SaveTrivia()
    #Start up a new question, avoiding using the same question twice in a row
    global current_question_index
    if previous_question_index != -1 and questions_list.count > 1:
        while True:
            current_question_index = Parent.GetRandom(0,len(questions_list))
            if current_question_index != previous_question_index: break
    else: 
        current_question_index = Parent.GetRandom(0,len(questions_list))
    if ScriptSettings.EnableDebug: Log("INFO: Question at Index " + str(current_question_index + 1) + " loaded.")
    Post(ParseString(ScriptSettings.QuestionString))

def CheckForMatch(data):
    current_question = questions_list[current_question_index]
    current_answers = current_question.get_answers()
    for answer in current_answers:
        if data.Message.lower() == answer.lower():
            return True
    return False

def GetAttribute(attribute, message):
    attribute = attribute + ":"
    #The start index of the attribute begins at the end of the attribute designator, such as "game:"
    try:
        index_of_beginning_of_attribute = message.lower().index(attribute) + len(attribute)
    except ValueError as ex:
        #If the missing attribute was Points, use the default point value
        if attribute.lower() == "points:":
            return ScriptSettings.QuestionDefaultPointValue
        raise ex
    #The end index of the attribute is at the last space before the next attribute designator, or at the end of the message
    try:
        index_of_end_of_attribute = message[index_of_beginning_of_attribute:index_of_beginning_of_attribute + message[index_of_beginning_of_attribute:].index(":")].rindex(" ")
    except ValueError:
        #If this error is thrown, the end of the message was hit, so just return all of the remaining message
        return message[index_of_beginning_of_attribute:].strip()
    return message[index_of_beginning_of_attribute:index_of_beginning_of_attribute + index_of_end_of_attribute].strip()

def ParseString(string, data = None):
    #Apply question attributes to a string
    string = string.replace("$index", str(current_question_index + 1))
    string = string.replace("$currency", str(Parent.GetCurrencyName()))
    string = string.replace("$question", questions_list[current_question_index].get_question())
    string = string.replace("$points", str(questions_list[current_question_index].get_points()))
    string = string.replace("$answers", ",".join(questions_list[current_question_index].get_answers()))
    string = string.replace("$game", questions_list[current_question_index].get_game())

    if not data == None:
        string = str(string).replace("$user", data.UserName)

    return string

def SaveTrivia():
    try:        
        #if the trivia file does not exist, create it
        if not os.path.exists(questions_file):
            with io.open(questions_file, 'w') as outfile:
                outfile.write(json.dumps({}))

        #record the questions
        with open (questions_file, 'w') as outfile:
            outfile.seek(0)
            #When writing the Questions to disk, use the Question.toJSON() function
            json.dump(questions_list, outfile, indent=4, default=lambda q: q.toJSON())
            outfile.truncate()
    except OSError as e:
        Log("ERROR: Unable to save trivia questions! " + e.message)

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
            if ScriptSettings.EnableDebug: Log("Questions loaded: " + str(len(questions_list)))
        except ValueError:
            if ScriptSettings.EnableDebug: Log("Question file exists, but contains no data.")
    else:
        if ScriptSettings.EnableDebug: Log("WARNING: No questions file exists.")

#Reload Settings (Called when a user clicks the Save Settings button in the Chatbot UI)
def ReloadSettings(jsonData):
    # Execute json reloading here
    if ScriptSettings.EnableDebug: Log("Saving settings.")

    global ScriptSettings
    ScriptSettings.__dict__ = json.loads(jsonData)
    ScriptSettings.Save(settings_file)

    if ScriptSettings.EnableDebug: Log("Settings saved successfully")

    return

def Log(message):
    Parent.Log(ScriptName, message)

def Post(message):
    Parent.SendStreamMessage(message)