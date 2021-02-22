# Trivia

Play trivia in Twitch Chat! Winners get Chatbot currency or just bragging rights.

## Installing

This script was built for use with Streamlabs Chatbot.
Follow instructions on how to install custom script packs at:
https://github.com/StreamlabsSupport/Streamlabs-Chatbot/wiki/Prepare-&-Import-Scripts

## Use

### Options

-Only Run When Live: Allows/disallows trivia to run when offline. (Default: True)

-Permissions to Play: Sets the permissions required for a chatter to play trivia. (Default: Everyone)
  
-Permissions to Modify: Sets the permissions required for a chatter to add, remove, and modify questions. (Default: Moderator)

-Question Delay: The amount of time (in minutes) between questions. (Default: queue)

-Question Format: How the trivia questions are displayed. (Parameters: $index, $points, $currency, $game, $question, $answers) (Default: Win $points $currency by answering: In $game, $question)
  
-Successful Answer Format: The string displayed on correct answer. (Parameters: $index, $points, $currency, $game, $question, $answers, $user) (Default: $user has answered correctly and won $points $currency.)

-ShowAnswersOnFailure: Show the question's answer(s) when the question expires. (Default: False)

-Failure to Answer Format: How the trivia answers are displayed on expiry. (Parameters: $index, $points, $currency, $game, $question, $answers) (Default: Nobody answered the previous question. The answers were $answers.)

-Loyalty Point Rewards: Correct trivia answers reward loyalty points. (Default: True)

-Default Question Values: The default point value a question will have if none is supplied. (Default: 50)

-% Point Decrease On Correct Answer: Future currency reward amount will decrease by this percentage when somebody correctly answers a question. Lowers the value of easy questions. (Default: 10)

-Enable Chat Confirmations: Enable or disable chat messages that confirm successful command usages. (Default: False)

-Enable Syntax Hints: Enable or disable syntax hints for when somebody uses a command improperly (Missing arguments, etc.). (Default: False)

-Enable Chat Errors: Enable or disable chat messages for command errors (Not A Number, Insufficient Permissions, etc.). (Default: False)

-Enable Debug: Enable or disable debug logs. (Default: False)

### Commands

WIP

## Authors

Crimdahl - [Twitch](https://www.twitch.tv/crimdahl), [Twitter](https://www.twitter.com/crimdahl)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
