FROM python:3.14-bookworm as base

# The following is adapted from:
# https://sourcery.ai/blog/python-docker/

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1

FROM base AS python-deps

# Install pipenv and compilation dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc wget
RUN pip install pipenv
RUN wget https://github.com/ddvk/rmapi/releases/download/v0.0.32/rmapi-linux-amd64.tar.gz

RUN tar xvzf rmapi-linux-amd64.tar.gz

RUN mkdir -p /base
WORKDIR /base

# Install python dependencies in /.venv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy
FROM base AS runtime

# Copy virtualenv from python-deps stage
COPY --from=python-deps /base/.venv /base/.venv
COPY --from=python-deps /rmapi /base/.venv/bin/rmapi
ENV PATH="/base/.venv/bin:$PATH"

RUN playwright install-deps
RUN playwright install

# Create and switch to a new user
RUN useradd --create-home appuser
RUN mkdir -p /home/appuser/.cache/
RUN cp -r /root/.cache/ms-playwright /home/appuser/.cache/
RUN chown -R appuser /home/appuser/.cache
WORKDIR /home/appuser
USER appuser

# Install application into container
COPY . .

# Run the application
ENTRYPOINT ["python3", "-u", "main.py"]