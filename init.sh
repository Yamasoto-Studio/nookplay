#!/bin/bash
# Run once to initialize the database
python -c "from app import init_db; init_db(); print('Database initialized.')"
