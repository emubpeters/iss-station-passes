## Overview
This script should read a Google calendar for the next 20 events, and display any passes of the International Space Station over that event.  It will report which will be visible (if any) and ones that will not be, with reasons why.

## Requirements
* Python 2.7+
* Google API key

## Instructions
1. Log into the Google developer console
2. Create a new project (name: ISS Station Passes)
3. Create OAuth credentials
4. Download the JSON file to client_secret.json in this script folder
5. Enable the Google Maps API for the project
6. Enable the calendar API for the project

## Known Issues
* Event locations are not always 100% accurate