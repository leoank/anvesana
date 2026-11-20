set pagination off
set confirm off
set follow-fork-mode parent
set detach-on-fork on
handle SIGUSR1 SIGCHLD SIGPIPE nostop noprint pass
catch syscall ioctl
commands
silent
continue
end
run
quit
