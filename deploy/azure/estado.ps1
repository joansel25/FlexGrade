# ¿Hay algo encendido en Azure, y cuanto lleva costando?
#
#   .\deploy\azure\estado.ps1
#
# Envoltorio para PowerShell: la logica vive en estado.sh, el mismo archivo que se usa en Linux
# y en el CI. Aqui no se duplica nada.

. "$PSScriptRoot\_bash.ps1"
Invoke-ScriptBash -Script "estado.sh" -Argumentos $args
