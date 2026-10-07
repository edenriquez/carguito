from __future__ import annotations

import logging

from functools import cached_property

from ..adapters.outbound.crypto import FileIngestKeyring
from ..adapters.outbound.cube import DuckDbCube, DuckDbMetricEngine
from ..adapters.outbound.extraction import (
    KeywordTemplateClassifier,
    PdfExtractor,
    SatXmlExtractor,
)
from ..adapters.outbound.chat import FallbackChat, NullChat, OpenAiCompatibleChat
from ..adapters.outbound.decisions import TypeSafeDecisions
from ..adapters.outbound.metrics import (
    CohortProfileResolver,
    FinancialAdviceResolver,
    InvestmentProjectionResolver,
)
from ..adapters.outbound.parsing import DefaultParserFactory
from ..adapters.outbound.receipts import (
    HeuristicReceiptReader,
    LlmReceiptReader,
    RapidOcrReceiptOcr,
)
from ..adapters.outbound.references import (
    AmazonListingsReference,
    BraveSearch,
    FirecrawlSearch,
    ProfecoPriceReference,
    WebPriceReference,
)
from ..application.ports.outbound.decisions import NullDecisions
from ..application.ports.outbound.references import (
    CompositePriceReference,
    NullPriceReference,
    PriceReference,
)
from ..adapters.outbound.persistence import (
    Database,
    SqlAccountRepository,
    SqlCategoryRepository,
    SqlDashboardRepository,
    SqlGoalRepository,
    SqlMerchantRepository,
    SqlProductReferenceTermRepository,
    SqlReceiptRepository,
    SqlUiEventRepository,
    SqlStatementRepository,
    SqlTagRepository,
    SqlTransactionRepository,
    SqlUserAliasRepository,
    SqlUserLabelRepository,
    SqlUserTransferPartyRepository,
    SqlConversationRepository,
    SqlWorkstationRepository,
)
from ..adapters.outbound.persistence.migrator import upgrade_to_head
from ..adapters.outbound.persistence.seed import seed_reference_data
from ..adapters.outbound.storage import TransientFileStorage
from ..application.use_cases import (
    AnswerPriceQuestion,
    ComparePricesUseCase,
    CreateCategoryUseCase,
    ResolveProductTerms,
    DetectRecurringUseCase,
    ListAttentionUseCase,
    GetForecastUseCase,
    GetHomeDashboardUseCase,
    GetMetricCatalogUseCase,
    GetSpendingSummaryUseCase,
    ListTransactionsUseCase,
    IngestReceiptImageUseCase,
    IngestReceiptUseCase,
    ManageGoalsUseCase,
    ManageReceiptsUseCase,
    ManageStatementsUseCase,
    ManageTagsUseCase,
    AnswerWorkstationQuestion,
    ManageConversations,
    ManageWorkstations,
    MarkTransferPartyUseCase,
    PairTransfersUseCase,
    ProcessExtractedUseCase,
    ProcessFileUseCase,
    RealiasUseCase,
    RebuildCubeUseCase,
    RecategorizeUseCase,
    RunMetricQueriesUseCase,
    SaveHomeDashboardUseCase,
    SimulateForecastUseCase,
    UpdateTransactionUseCase,
)
from .settings import Settings


logger = logging.getLogger(__name__)


class Container:
    """Composition root: wires adapters into use cases.

    This is the only place allowed to know about both concrete adapters and
    application use cases. Everything else depends on interfaces.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # --- infrastructure singletons --------------------------------------
    @cached_property
    def database(self) -> Database:
        return Database(self.settings.database_url)

    @cached_property
    def cube(self) -> DuckDbCube:
        return DuckDbCube(self.settings.cube_path)

    @cached_property
    def metric_engine(self) -> DuckDbMetricEngine:
        # Borrows the cube's connection rather than opening its own: DuckDB is
        # single-writer per file.
        return DuckDbMetricEngine(self.cube)

    @cached_property
    def metric_resolvers(self) -> list:
        """Computed metrics. One entry per metric that is a Python function."""
        # The advice resolver reads the monthly series *through* the engine
        # rather than issuing its own SQL, so the measure-level default filters
        # (transfers, excluded rows) apply to it by construction.
        return [
            InvestmentProjectionResolver(),
            FinancialAdviceResolver(self.metric_engine),
            CohortProfileResolver(self.metric_engine),
        ]

    @cached_property
    def file_storage(self) -> TransientFileStorage:
        return TransientFileStorage()

    @cached_property
    def ingest_keyring(self) -> FileIngestKeyring:
        """The server's identity for sealed device ingest. Minted on bootstrap."""
        return FileIngestKeyring(self.settings.ingest_key_path)

    # --- repositories ----------------------------------------------------
    @cached_property
    def transactions(self) -> SqlTransactionRepository:
        return SqlTransactionRepository(self.database)

    @cached_property
    def statements(self) -> SqlStatementRepository:
        return SqlStatementRepository(self.database)

    @cached_property
    def receipts(self) -> SqlReceiptRepository:
        return SqlReceiptRepository(self.database)

    @cached_property
    def ui_events(self) -> SqlUiEventRepository:
        return SqlUiEventRepository(self.database)

    @cached_property
    def accounts(self) -> SqlAccountRepository:
        return SqlAccountRepository(self.database)

    @cached_property
    def goals_repo(self) -> SqlGoalRepository:
        return SqlGoalRepository(self.database)

    @cached_property
    def dashboards(self) -> SqlDashboardRepository:
        return SqlDashboardRepository(self.database)

    @cached_property
    def tags(self) -> SqlTagRepository:
        return SqlTagRepository(self.database)

    @cached_property
    def workstations(self) -> SqlWorkstationRepository:
        return SqlWorkstationRepository(self.database)

    @cached_property
    def conversations(self) -> SqlConversationRepository:
        return SqlConversationRepository(self.database)

    @cached_property
    def categories(self) -> SqlCategoryRepository:
        return SqlCategoryRepository(self.database)

    @cached_property
    def merchants(self) -> SqlMerchantRepository:
        return SqlMerchantRepository(self.database)

    @cached_property
    def user_labels(self) -> SqlUserLabelRepository:
        return SqlUserLabelRepository(self.database)

    @cached_property
    def user_aliases(self) -> SqlUserAliasRepository:
        return SqlUserAliasRepository(self.database)

    @cached_property
    def user_transfer_parties(self) -> SqlUserTransferPartyRepository:
        return SqlUserTransferPartyRepository(self.database)

    # --- pipeline components --------------------------------------------
    @cached_property
    def classifier(self) -> KeywordTemplateClassifier:
        return KeywordTemplateClassifier()

    @cached_property
    def parser_factory(self) -> DefaultParserFactory:
        return DefaultParserFactory()

    @cached_property
    def extractors(self) -> list:
        # Order matters: XML is matched before the PDF extractor.
        return [SatXmlExtractor(), PdfExtractor()]

    # --- use cases -------------------------------------------------------
    @cached_property
    def process_file(self) -> ProcessFileUseCase:
        return ProcessFileUseCase(
            extractors=self.extractors,
            classifier=self.classifier,
            parser_factory=self.parser_factory,
            statements=self.statements,
            transactions=self.transactions,
            categories=self.categories,
            merchants=self.merchants,
            user_labels=self.user_labels,
            user_aliases=self.user_aliases,
            transfer_parties=self.user_transfer_parties,
            cube=self.cube,
            file_storage=self.file_storage,
        )

    @cached_property
    def process_extracted(self) -> ProcessExtractedUseCase:
        # Same collaborators as `process_file` minus the two the device path
        # has no use for: nothing to extract, nothing to store transiently.
        return ProcessExtractedUseCase(
            classifier=self.classifier,
            parser_factory=self.parser_factory,
            statements=self.statements,
            transactions=self.transactions,
            categories=self.categories,
            merchants=self.merchants,
            user_labels=self.user_labels,
            user_aliases=self.user_aliases,
            transfer_parties=self.user_transfer_parties,
            cube=self.cube,
        )

    @cached_property
    def manage_statements(self) -> ManageStatementsUseCase:
        return ManageStatementsUseCase(
            statements=self.statements,
            transactions=self.transactions,
            # So deleting a statement detaches its tickets instead of leaving
            # them pointing at rows that no longer exist.
            receipts=self.receipts,
            cube=self.cube,
        )

    @cached_property
    def list_transactions(self) -> ListTransactionsUseCase:
        return ListTransactionsUseCase(self.transactions)

    @cached_property
    def update_transaction(self) -> UpdateTransactionUseCase:
        return UpdateTransactionUseCase(
            transactions=self.transactions,
            categories=self.categories,
            cube=self.cube,
        )

    @cached_property
    def realias(self) -> RealiasUseCase:
        return RealiasUseCase(
            transactions=self.transactions,
            user_aliases=self.user_aliases,
            cube=self.cube,
        )

    @cached_property
    def recategorize(self) -> RecategorizeUseCase:
        return RecategorizeUseCase(
            transactions=self.transactions,
            categories=self.categories,
            user_labels=self.user_labels,
            cube=self.cube,
        )

    @cached_property
    def create_category(self) -> CreateCategoryUseCase:
        return CreateCategoryUseCase(categories=self.categories, cube=self.cube)

    @cached_property
    def mark_transfer(self) -> MarkTransferPartyUseCase:
        return MarkTransferPartyUseCase(
            transactions=self.transactions,
            transfer_parties=self.user_transfer_parties,
            cube=self.cube,
        )

    @cached_property
    def pair_transfers(self) -> PairTransfersUseCase:
        return PairTransfersUseCase(
            transactions=self.transactions,
            cube=self.cube,
        )

    @cached_property
    def chat(self):
        """The LLM seam, or a null object when nothing is configured.

        Injected rather than constructed at the call site so "no key set" is a
        wiring decision made once, and every caller sees the same `available`
        flag instead of each re-reading the environment.
        """
        settings = self.settings
        if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
            primary = OpenAiCompatibleChat(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
            )
            fallback_name = settings.llm_fallback_model.strip()
            if fallback_name and fallback_name != settings.llm_model:
                return FallbackChat(
                    primary,
                    OpenAiCompatibleChat(
                        base_url=settings.llm_base_url,
                        api_key=settings.llm_api_key,
                        model=fallback_name,
                    ),
                )
            return primary
        return NullChat()

    @cached_property
    def decisions(self):
        """The typed-decision seam, or a null object when no key is set.

        Separate from :meth:`chat` on purpose and not a fallback for it: one
        streams words for a person to read, the other returns a value for code
        to switch on. A deployment may have either, both or neither, and every
        caller is written for all four.
        """
        settings = self.settings
        if settings.typesafe_api_key and settings.typesafe_model:
            return TypeSafeDecisions(
                api_key=settings.typesafe_api_key,
                model=settings.typesafe_model,
                base_url=settings.typesafe_base_url,
            )
        return NullDecisions()

    @cached_property
    def receipt_reader(self):
        """Who turns OCR lines into products.

        The model when one is configured, the regexes otherwise — and the model
        one falls back to the regexes on its own whenever its answer does not
        survive checking, so this is a preference, never a dependency.
        """
        if self.chat.available:
            return LlmReceiptReader(self.chat, HeuristicReceiptReader())
        return HeuristicReceiptReader()

    @cached_property
    def ingest_receipt(self) -> IngestReceiptUseCase:
        return IngestReceiptUseCase(
            reader=self.receipt_reader,
            receipts=self.receipts,
            transactions=self.transactions,
        )

    @cached_property
    def receipt_ocr(self):
        """Who reads a ticket *photo*, for uploads from the web.

        RapidOCR when its wheels are installed (the ``receipts`` extra), else
        nothing: the upload endpoint then answers 503 and says what to
        install. The phone never needs this; it reads its own photos.
        """
        if RapidOcrReceiptOcr.available():
            return RapidOcrReceiptOcr()
        logger.info("receipt ocr: rapidocr not installed; web ticket upload disabled")
        return None

    @cached_property
    def ingest_receipt_image(self) -> IngestReceiptImageUseCase:
        return IngestReceiptImageUseCase(ocr=self.receipt_ocr, ingest=self.ingest_receipt)

    @cached_property
    def manage_receipts(self) -> ManageReceiptsUseCase:
        return ManageReceiptsUseCase(
            receipts=self.receipts,
            transactions=self.transactions,
        )

    @cached_property
    def compare_prices(self) -> ComparePricesUseCase:
        # No cube: a price book is built from receipt lines, which the cube
        # does not hold — it aggregates movements, and a movement is one number
        # for a whole basket.
        return ComparePricesUseCase(self.receipts)

    @cached_property
    def price_reference(self) -> PriceReference:
        """External reference prices, or nothing.

        Nothing is a first-class option: an empty city means the chat makes no
        outbound call at all, and every answer is built from the user's own
        tickets exactly as it was before this port existed.
        """
        sources: list[PriceReference] = []
        city = self.settings.price_reference_city.strip()
        if city:
            sources.append(ProfecoPriceReference(city=city))
        listings = self.settings.listings_source.strip().lower()
        if listings == "amazon":
            sources.append(AmazonListingsReference())
        elif listings == "brave":
            # Extraction rides on the chat port; with no model configured the
            # composite drops this source by its own `available`.
            sources.append(WebPriceReference(
                BraveSearch(self.settings.brave_search_api_key.strip()), self.chat, engine="Brave"
            ))
        elif listings == "firecrawl":
            sources.append(WebPriceReference(
                FirecrawlSearch(self.settings.firecrawl_api_key.strip()),
                self.chat, engine="Firecrawl", fallback=self.listings_reader_fallback,
            ))
        composite = CompositePriceReference(sources)
        return composite if composite.available else NullPriceReference()

    @cached_property
    def product_reference_terms(self) -> SqlProductReferenceTermRepository:
        return SqlProductReferenceTermRepository(self.database)

    @cached_property
    def resolve_product_terms(self) -> ResolveProductTerms:
        """The association between a ticket's shorthand and the world's word.

        Given both model seams, which do different halves of the job: the typed
        one chooses among words already in use, the text one invents the ones
        nobody has needed yet. With neither configured it proposes nothing, the
        screen says "sin asociar", and the user can still type the term.
        """
        return ResolveProductTerms(
            self.product_reference_terms, self.chat, self.decisions
        )

    @cached_property
    def listings_reader_fallback(self):
        """A second model to read store pages with when the main one says 429.

        Same gateway and key, different model; ``None`` when unconfigured or
        when it would be the same model twice.
        """
        model = self.settings.listings_reader_fallback_model.strip()
        if not model or model == self.settings.llm_model or not self.chat.available:
            return None
        return OpenAiCompatibleChat(
            base_url=self.settings.llm_base_url, api_key=self.settings.llm_api_key, model=model
        )

    @cached_property
    def answer_price_question(self) -> AnswerPriceQuestion:
        return AnswerPriceQuestion(
            chat=self.chat,
            compare=self.compare_prices,
            references=self.price_reference,
            product_terms=self.resolve_product_terms,
        )

    @cached_property
    def answer_workstation_question(self) -> AnswerWorkstationQuestion:
        return AnswerWorkstationQuestion(
            chat=self.chat,
            engine=self.metric_engine,
            profile_resolver=CohortProfileResolver(self.metric_engine),
            transactions=self.transactions,
        )

    @cached_property
    def manage_workstations(self) -> ManageWorkstations:
        # No cube and no engine: a workstation stores a *question*. Reading it
        # is the ordinary metric path with the rule handed over as filters.
        return ManageWorkstations(
            workstations=self.workstations,
            # So deleting a lens also deletes its chat threads.
            conversations=self.conversations,
        )

    @cached_property
    def manage_conversations(self) -> ManageConversations:
        return ManageConversations(conversations=self.conversations)

    @cached_property
    def manage_tags(self) -> ManageTagsUseCase:
        return ManageTagsUseCase(
            tags=self.tags,
            transactions=self.transactions,
            cube=self.cube,
        )

    @cached_property
    def spending_summary(self) -> GetSpendingSummaryUseCase:
        return GetSpendingSummaryUseCase(self.cube)

    @cached_property
    def run_metric_queries(self) -> RunMetricQueriesUseCase:
        return RunMetricQueriesUseCase(
            engine=self.metric_engine, resolvers=self.metric_resolvers
        )

    @cached_property
    def metric_catalog(self) -> GetMetricCatalogUseCase:
        return GetMetricCatalogUseCase()

    @cached_property
    def get_home_dashboard(self) -> GetHomeDashboardUseCase:
        return GetHomeDashboardUseCase(self.dashboards)

    @cached_property
    def save_home_dashboard(self) -> SaveHomeDashboardUseCase:
        return SaveHomeDashboardUseCase(self.dashboards)

    @cached_property
    def detect_recurring(self) -> DetectRecurringUseCase:
        return DetectRecurringUseCase(self.transactions, self.user_aliases)

    @cached_property
    def list_attention(self) -> ListAttentionUseCase:
        return ListAttentionUseCase(self.transactions)

    @cached_property
    def get_forecast(self) -> GetForecastUseCase:
        return GetForecastUseCase(self.cube)

    @cached_property
    def simulate_forecast(self) -> SimulateForecastUseCase:
        return SimulateForecastUseCase()

    @cached_property
    def rebuild_cube(self) -> RebuildCubeUseCase:
        return RebuildCubeUseCase(self.transactions, self.cube, self.tags)

    @cached_property
    def manage_goals(self) -> ManageGoalsUseCase:
        return ManageGoalsUseCase(self.goals_repo)

    # --- bootstrap -------------------------------------------------------
    def bootstrap(self) -> None:
        """Migrate the schema, mint the ingest key, seed reference data + cube."""
        # Minted here rather than on the first `GET /api/ingest/key` so that a
        # cold server never answers that request with a key it just generated
        # under a request lock — and so the operator sees the file appear at
        # startup, not at first phone contact.
        self.ingest_keyring.ensure()
        if self.settings.run_migrations:
            upgrade_to_head(self.database, self.settings.database_url)
        else:
            # Test path only: a fresh throwaway database per test, where
            # replaying migration history would test Alembic, not the app.
            self.database.create_all()
        seed_reference_data(self.categories, self.merchants)
        self.cube.sync_categories(self.categories.get_all())
