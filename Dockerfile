FROM python:3.10-slim as base

# The following is adapted from:
# https://sourcery.ai/blog/python-docker/

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1

FROM base AS python-deps

# Install pipenv and compilation dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc wget software-properties-common sudo
RUN pip install pipenv
RUN wget https://github.com/juruen/rmapi/releases/download/v0.0.25/rmapi-linuxx86-64.tar.gz
RUN tar xvzf rmapi-linuxx86-64.tar.gz

RUN mkdir -p /base
WORKDIR /base

# Install python dependencies in /.venv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy
RUN playwright install
RUN sudo playwright install-deps

FROM base AS runtime

# Copy virtualenv from python-deps stage
COPY --from=python-deps /base/.venv /base/.venv
COPY --from=python-deps /rmapi /base/.venv/bin/rmapi
ENV PATH="/base/.venv/bin:$PATH"

# Create and switch to a new user
RUN useradd --create-home appuser
WORKDIR /home/appuser
USER appuser

# Install application into container
COPY . .

# Run the application
ENTRYPOINT ["python3", "-u", "main.py"]