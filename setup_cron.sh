#!/bin/bash
# Configura un job diario a las 10:00 AM que actualiza la cartelera.
# Uso: bash setup_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"
LOG="$SCRIPT_DIR/data/cron.log"
CRON_CMD="0 10 * * * cd \"$SCRIPT_DIR\" && $PYTHON run.py >> \"$LOG\" 2>&1"

# Agregar si no existe ya
( crontab -l 2>/dev/null | grep -v "cines/run.py" ; echo "$CRON_CMD" ) | crontab -
echo "✅ Cron configurado:"
echo "   $CRON_CMD"
echo ""
echo "Para ver los logs: tail -f $LOG"
echo "Para editar: crontab -e"
echo "Para eliminar: crontab -l | grep -v 'cines/run.py' | crontab -"
