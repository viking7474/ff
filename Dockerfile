FROM ubuntu:22.04
WORKDIR /app
COPY . /app
ENV DEBIAN_FRONTEND=noninteractive

RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    printf 'deb http://mirror.bizflycloud.vn/ubuntu jammy main restricted universe multiverse\ndeb http://mirror.bizflycloud.vn/ubuntu jammy-updates main restricted universe multiverse\ndeb http://mirror.bizflycloud.vn/ubuntu jammy-backports main restricted universe multiverse\ndeb http://mirror.bizflycloud.vn/ubuntu jammy-security main restricted universe multiverse\n' \
    > /etc/apt/sources.list && \
    apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --fix-missing \
        build-essential \
        make \
        msitools \
        wget \
        unzip \
        rustc \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        git \
        p7zip-full \
        golang-go \
        aria2 \
        curl \
        rsync \
        libsqlite3-dev \
        ca-certificates \
    && update-ca-certificates

RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN git config --global user.email "build@camoufox" && \
    git config --global user.name "Camoufox Build"

RUN make setup

RUN python3 -c "\
content = open('winfox-149.0-beta.25/python/mach/mach/site.py').read();\
old = '        if self._site_packages_source != SitePackagesSource.VENV:\n            pass\n\n        self._virtualenv()';\
new = '        if self._site_packages_source != SitePackagesSource.VENV:\n            return\n\n        self._virtualenv()';\
content = content.replace(old, new);\
open('winfox-149.0-beta.25/python/mach/mach/site.py', 'w').write(content)\
"

RUN pip3 install zstandard

RUN apt-get update && apt-get install -y \
    meson \
    ninja-build \
    pkg-config \
    libcairo2-dev \
    python3-dev

RUN apt-get remove -y meson

RUN pip3 install -U "meson>=0.63.3" ninja

RUN pip3 install pycairo

RUN pip3 install taskcluster

RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y \
        libc6:i386 \
        libstdc++6:i386 \
        zlib1g:i386

RUN apt-get install -y watchman || true

RUN make mozbootstrap && \
    mkdir -p /app/dist

VOLUME /root/.mozbuild
VOLUME /app/dist
ENTRYPOINT ["python3", "./multibuild.py"]
