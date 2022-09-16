# Dockerfile to replicate the CI run in the docker container

FROM archlinux
RUN pacman --noconfirm -Syu
RUN pacman --noconfirm -S git
COPY ./tests/ci_arch_pacman.sh ci_arch_pacman.sh
COPY ./tests/ci_general_deps.sh ci_general_deps.sh
COPY conanfile.txt conanfile.txt
RUN ./ci_arch_pacman.sh
# Running conan in the image purely in order to save some time on the
# container tests runs
RUN ./ci_general_deps.sh
