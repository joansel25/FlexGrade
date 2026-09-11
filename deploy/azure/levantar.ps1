# Levanta la infraestructura completa en Azure.
#
#   .\deploy\azure\levantar.ps1                 perfil economico (~0,071 USD/hora)
#   .\deploy\azure\levantar.ps1 demo            perfil de sustentacion (~1,03 USD/hora)
#   .\deploy\azure\levantar.ps1 demo --ensayo   muestra que se crearia, sin crear nada (0 USD)
#   .\deploy\azure\levantar.ps1 demo --pico     ademas arranca ya en 6 instancias
#
# Envoltorio para PowerShell: la logica vive en levantar.sh, el mismo archivo que se usa en Linux
# y en el CI. Aqui no se duplica nada.

. "$PSScriptRoot\_bash.ps1"
Invoke-ScriptBash -Script "levantar.sh" -Argumentos $args
