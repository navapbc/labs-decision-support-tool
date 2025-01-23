# This file is sourced when `make app-shell` is called to set up the shell environment

# Save the commandline history for future runs
export HISTFILE="$PWD"/.app-shell.bash_history

# Prepend blank line and "(app-shell)" to bash prompt
export PS1="\n(app-shell) ${debian_chroot:+($debian_chroot)}\u:\w\$ "

# Set iTerm's title
function title {
    echo -ne "\033]0;"$*"\007"
}
title "App shell"

# Print make targets
make help

# Load personalized local configuration
[ -f .app-shell.bashrc_local ] && . .app-shell.bashrc_local
