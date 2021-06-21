# Trivia

Play trivia in Twitch Chat! Winners get Chatbot currency or just bragging rights.

## Installing

This script was built for use with Streamlabs Chatbot.
Follow instructions on how to install custom script packs at:
https://github.com/StreamlabsSupport/Streamlabs-Chatbot/wiki/Prepare-&-Import-Scripts

## Settings

-Only Run When Live: Allows/disallows trivia to run when offline. (Default: True)

-Permissions to Play: Sets the permissions required for a chatter to play trivia. (Default: Everyone)
  
-Permissions to Modify: Sets the permissions required for a chatter to add, remove, and modify questions. (Default: Moderator)

### Question Settings

-Question Duration in Minutes: Amount of time (in minutes) questions last. (Default: 5)

-Delay Between Questions in Minutes: The amount of time (in minutes) between questions. (Default: 5)

-Auto-run Questions: Automatically run the next question? If false, users have to type !trivia to start the next question. (Default: True)

-Delay Between Ready Notifications in Minutes: If not auto-running questions, the amount of time between recurring chat notifications that a question is available. (Default: 10)

-Question String Format: How the trivia questions are displayed in Standard Mode. Parameters: $index, $points, $currency, $game, $question, $answers (Default: Win $points $currency by answering: In $game, $question)
  
-Reward String Format: The string displayed when somebody correctly answers in Standard Mode. Parameters: $index, $points, $currency, $game, $question, $answers, $users (Default: $user has answered correctly and won $points $currency.)

-Expiration String Format: How the trivia answers are displayed on expiry. Parameters: $index, $points, $currency, $game, $question, $answers (Default: Nobody answered the previous question. The answers were $answers.)

### Game Detection

-Enable Game Detection: If enabled, queries Twitch's API to get the last known game on the channel of the person whose name is in Twitch Username, then filters questions by that game. (Default: False)

-Twitch Username: Probably your username, used to fetch your last recorded game. (Default: "")

### Arena Settings

-Use Arena Mode: Questions do not end after the first correct answer. All correct answers within the questions duration are rewarded at the end. (Default: False)

-Divide Points Among Winners: When multiple people correctly answer, should the reward points be divided among them? (Default: False)

### Reward Settings

-Enable Loyalty Point Rewards: Correct trivia answers reward loyalty points. (Default: True)

-Default Question Value: The default point value a question will have if none is supplied. (Default: 50)

-Reward Scaling: Random = questions reward a random percentage range of their base value as a reward. Percentage = points increase/decrease by a percentage of their value permanently when the question is answered/unanswered. (Default: Off)

-Random Scaling: Lower Bound Percentage: When using random scaling, the lower bound of possible point values is determined by this percentage. (Default: 50)

-Random Scaling: Upper Bound Percentage: When using random scaling, the upper bound of possible point values is determined by this percentage. (Default: 200)

-Percentage Scaling: Point Decrease Percent on Answered: Future currency reward amount will decrease by this percentage when somebody correctly answers a question. Lowers the value of easy questions. (Default: 5)

-Percentage Scaling: Point Increase Percent on Unanswered: Future currency reward amount will increase by this percentage when nobody correctly answers a question. Increases the value of hard questions. (Default: 10)

### Output Settings

-Write Question Text to File: Log the current question to a file, useful for displaying the question on screen with a Text widget. Disables most chat-based output. (Default: False)

-Enable File Logging: If enabled, will log to trivialog.txt in the script directory. (Default: False)

-Level of Chatbot Logging: Choose verbosity of chatbot logging. Higher levels include all lower levels. (Default: Warn)

## Commands

### <Blank>
Syntax: !trivia
Result: If a question is currently running, return the question (syntax determined by the Question Ask String) and an indicator of the remaining question duration. If there is no question AND Auto-Run Questions is off AND the next question is ready, loads and displays the next question.

### Start
Syntax: !trivia start
Result: Starts the trivia if the trivia has been paused with "!trivia stop".

### Stop
Syntax: !trivia stop
Result: Pauses trivia until restarted with "!trivia start".

### Count
Syntax: !trivia count
Result: Displays a count of all questions. If Game Detection is enabled, also displays the count of questions after filtering for the currently active game.

### Answers
Syntax: !trivia answers
Result: Displays a list of answers for the current question.

### Save
Syntax: !trivia save
Result: Manually saves the trivia to file.

### Load
Syntax: !trivia load
Result: Immediately ends any current question and loads a new question. Nobody is rewarded.

### Add
Syntax: !trivia (add game:<Game Name>,) (points:<Points>,) question:<Question>, answers:<Pipe-Separated List of Answers>
Result: Allows a new question to be added. Points are optional - the default point value in settings will be used if a value is excluded. If Game Detection is on, game is optional - your current game will be used.

### Remove
Syntax: !trivia remove <Question Index>
Result: Removes the question at the supplied index and saves the trivia to file. If the index supplied is the same as the currently running question, immediately ends the question without rewarding anyone.

### Modify
Syntax: !trivia modify <Question Index> (game:<New Value>,) (question:<New Value>,) (points:<New Value>,) (answers <add/remove/set>: <New Value>|<New Value>| ...)
Result: Modifies the question at the index, changing the old value(s) to the supplied values. If modifying the questions answers, answers can be added to the existing set of answers, removed from the existing set of answers, or you can replace the set of answers.

## Authors

Crimdahl - [Twitch](https://www.twitch.tv/crimdahl), [Twitter](https://www.twitter.com/crimdahl)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
