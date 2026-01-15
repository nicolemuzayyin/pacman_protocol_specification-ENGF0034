[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/oWULkxJG)
# ENGF0034 Assignment 5

Welcome to your protocol design assignment! This repository contains an alpha-release of a multi-player networked Pacman game that needs a better network protocol specification.

## Quick Start

1. Clone this repository to your local machine
2. Navigate to the source code: `cd multi_player/src`
3. Test the game (see "Running the Game" below)
4. Read the full assignment instructions in `assignment.pdf`

## Prerequisites

- Python 3 or newer
- `simpleaudio` (optional, for sound): `pip install simpleaudio`

## Game Files

The Pacman game implementation follows a Model/View/Controller design pattern. The main code is located in `multi_player/src/`:
- `pacman.py` - Main game launcher
- `pa_controller.py` - Game controller logic
- `pa_model.py` - Game model and state management
- `pa_view.py` - Game display and graphics
- `pa_network.py` - Existing networking code (the focus of your analysis)
- `pa_settings.py` - Game configuration settings

There is also a relay server in `pacman_server/`.

## Game Objective

This is a multi-player version of Pacman. You compete with other players for food and try to tempt ghosts to attack them. If your Pacman goes down the tunnel, it disappears from your screen and reappears on your opponent's screen (Remote mode).

## Submission Guidelines

**Do not submit code changes.**

- Export your final protocol specification as a **PDF file**.
- Submit the PDF via the submission link on the course **Moodle** page.

## Your Task

1. Analyse the existing "quick and dirty" protocol in `pa_network.py`.
2. Design a better protocol that is robust, secure, and efficient.
   - Must use TCP, UDP, or both.
   - Must NOT use `pickle`.
   - Must NOT use JSON, XML, or HTML.
3. Write a complete and unambiguous technical specification for your new protocol.

## Running the Game

### Client-Server Mode
One player acts as the server, the other as the client.

**Server:**
```bash
python3 pacman.py -r -s -p <passwd>
```

**Client:**
```bash
python3 pacman.py -r -c <ip_address> -p <passwd>
```

### Relay Server Mode
A relay server passes messages between two clients.

**Relay Server:**
```bash
cd ../../pacman_server
python3 pacman_server.py
```

**Clients:**
```bash
python3 pacman.py -r -c <relay_server_ip> -p <passwd>
```

## Assessment

This assignment is assessed via peer-marking on Moodle. You will be marked on:
- Conciseness
- Correctness
- Unambiguity
- Completeness
- Use of examples

## Troubleshooting

### Sound Issues
If you want the full experience with sound, ensure you have installed the audio package:
`pip install simpleaudio`

### Network Issues
You can test the game on a single computer by running the server (or relay) and client(s) in separate terminal windows using `localhost` or `127.0.0.1` as the IP address.
