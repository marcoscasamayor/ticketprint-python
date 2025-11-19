#!/bin/bash

cd /home/sc3/Documentos/TicketPrint/
export DISPLAY=:0
source venv/bin/activate
python3 ticketprint-new.py &