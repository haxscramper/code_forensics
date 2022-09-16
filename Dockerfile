# Dockerfile to replicate the CI run in the docker container

FROM archlinux
RUN pacman --noconfirm -Syu
RUN pacman --noconfirm -S git
COPY ./.github/workflows/ci_arch_pacman.sh ci_arch_pacman.sh
RUN ./ci_arch_pacman.sh
