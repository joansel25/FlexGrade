# Destruye la infraestructura efimera.
#
#   .\deploy\azure\destruir.ps1        pregunta antes
#   .\deploy\azure\destruir.ps1 --si   no pregunta
#
# Envoltorio para PowerShell: la logica vive en destruir.sh, el mismo archivo que se usa en Linux
# y en el CI. Aqui no se duplica nada.

. "$PSScriptRoot\_bash.ps1"
Invoke-ScriptBash -Script "destruir.sh" -Argumentos $args
