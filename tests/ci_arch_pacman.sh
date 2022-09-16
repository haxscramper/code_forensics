#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

pacman --noconfirm -S \
    gcc \
    clang \
    python-pip \
    base-devel \
    wget \
    curl \
    git \
    cmake \
    make \
    sudo \
    boost

echo $PWD
useradd nopass
mkdir /home/nopass
chown -R nopass /home/nopass
passwd -d nopass
echo ' nopass ALL=(ALL)   ALL' >>/etc/sudoers

cd /tmp
git clone https://aur.archlinux.org/consolas-font.git
chown -R nopass consolas-font
cd consolas-font
sudo -u nopass makepkg -si --noconfirm
