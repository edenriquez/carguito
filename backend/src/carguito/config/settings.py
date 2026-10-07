from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///tomin.db"
    cube_path: str = "tomin_cube.duckdb"
    # The device-ingest keypair (docs/custody-plan.md F1). A file rather than an
    # env var so first boot needs no ceremony, and outside git so the secret half
    # never ships with the code — see backend/.gitignore.
    ingest_key_path: str = "ingest_key.json"

    # When true (the default) Container.bootstrap() runs `alembic upgrade head`.
    # Tests set it false and use metadata.create_all instead: they build a fresh
    # throwaway SQLite file per test, so replaying the migration history would
    # only cost time and would test Alembic rather than the app.
    run_migrations: bool = True

    supabase_jwt_secret: str | None = None
    auth_disabled: bool = True
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"

    cors_origins: str = "*"

    # The one optional integration. Provider-agnostic on purpose: any endpoint
    # that speaks OpenAI-shaped Chat Completions works (OpenRouter, Groq, a
    # local Ollama), so switching is these three values and no code. All three
    # empty is the normal state of a fresh clone -- the Workspace view still
    # reads and only its chat band renders disabled.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # Same gateway and key, used when the primary refuses (rate limit, outage).
    llm_fallback_model: str = ""

    # --- Typed decisions (optional, independent of the chat above) ----------
    # A System One model: state in, a typed value out with the probability
    # distribution it came from. Not a chat model and not a substitute for one
    # -- it answers "which of these words names this product", never "explain
    # my spending". Used where the code today asks a text model for a decision
    # at temperature 0 and then validates the string with a regex.
    #
    # Empty key is the normal state of a fresh clone: every caller keeps the
    # path it had before this existed.
    typesafe_api_key: str = ""
    typesafe_model: str = "jev-latest"
    typesafe_base_url: str = "https://api.typesafe.ai/v1"

    # External reference prices (Profeco's public price survey). On by default
    # and harmless when unreachable: the lookup fails to an empty section and
    # the chat answers from the user's own tickets exactly as it did before.
    # Set the city to "" to switch the whole thing off and make no outbound call.
    #
    # 1502 is the Valle de México survey area. The catalogue of city codes is
    # the one qqp.profeco.gob.mx itself uses.
    price_reference_city: str = "1502"

    # Second reference source: store listings from the web.
    #   "amazon" reads Amazon México's public search page -- free, no key, no
    #            account, and a marketplace. Off by default: the page sits
    #            behind bot controls and worked when tried, which is not the
    #            same as being something to rely on.
    #   "brave"  searches store pages via Brave's Search API and reads prices
    #            with the configured model. Needs `brave_search_api_key` (the
    #            free tier asks for a card) and a model.
    #   "firecrawl" searches store pages and *renders* them (Firecrawl), then the
    #            configured model reads the price off the page. Free plan of
    #            1,000 credits a month, no card. Needs `firecrawl_api_key` and a
    #            model. The one route that produced supermarket prices.
    #   ""       no web listings; Profeco alone.
    listings_source: str = ""
    brave_search_api_key: str = ""
    firecrawl_api_key: str = ""
    # Reads prices off rendered pages when the main model is rate-limited on
    # this larger prompt. "openrouter/free" routes to whichever free model is
    # answering right now; "" disables the fallback.
    listings_reader_fallback_model: str = "openrouter/free"

    # Where the web dashboard lives, so the phone can hand the user a link to
    # the statement it just sealed and sent. The backend has no other reason to
    # know the frontend's address, which is exactly why it is configuration.
    frontend_url: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
