"""Dataset Service for aggregating and filtering datasets."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any

from app.models import Dataset
from app.services.fdp_client import FDPClient, FDPError


logger = logging.getLogger(__name__)


def humanize_label(raw: str) -> str:
    """Turn a bare identifier like 'RefugeeProtectionNeeds' into 'Refugee Protection Needs'.

    Best effort: splits camelCase / PascalCase, replaces underscores and hyphens
    with spaces, capitalizes each word's first letter. All-lowercase identifiers
    (e.g. 'humantrafficking') can't be split without a dictionary.
    """
    if not raw:
        return raw
    text = raw.replace('_', ' ').replace('-', ' ')
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=\D)(?=\d)', ' ', text)
    words = [w for w in text.split() if w]
    return ' '.join(w[0].upper() + w[1:] for w in words)


def application_key(ds) -> str:
    """Canonical key for grouping a catalog as an application.

    Accepts either a Dataset dataclass or a raw dict (cache representation).

    1. ``catalog_homepage`` — explicit upstream linkage, normalized URL.
    2. ``catalog_title`` (lowercased, whitespace-collapsed) — same-named
       catalogs across FDPs group together when no homepage is published.
    3. ``catalog_uri`` — last resort so orphan catalogs still appear.
    """
    def _get(name):
        if isinstance(ds, dict):
            return ds.get(name)
        return getattr(ds, name, None)

    hp = _get('catalog_homepage')
    if hp:
        return 'hp:' + hp
    title = _get('catalog_title')
    if title:
        return 'title:' + ' '.join(title.lower().split())
    uri = _get('catalog_uri')
    if uri:
        return 'uri:' + uri
    return ''


@dataclass
class Source:
    """A connected FDP, aggregated for the browse-page source chip row."""

    fdp_uri: str
    fdp_title: str
    count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'fdp_uri': self.fdp_uri,
            'fdp_title': self.fdp_title,
            'count': self.count,
        }


@dataclass
class Theme:
    """Represents a theme for filtering datasets."""

    uri: str
    label: str
    count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'uri': self.uri,
            'label': self.label,
            'count': self.count,
        }


@dataclass
class Application:
    """Represents an 'application' — a catalog identity shared across FDPs.

    Catalogs are grouped by ``application_key()``: explicit catalog_homepage
    when published, otherwise normalized catalog_title, otherwise catalog_uri.
    The label is the most common ``catalog_title`` seen for that key.
    """

    key: str
    label: str
    fdp_count: int
    dataset_count: int
    # Kept for backwards compat with templates that still reference .homepage
    homepage: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key,
            'homepage': self.homepage,
            'label': self.label,
            'fdp_count': self.fdp_count,
            'dataset_count': self.dataset_count,
        }


class DatasetService:
    """Service for aggregating and filtering datasets from FDPs."""

    def __init__(self, fdp_client: FDPClient):
        """
        Initialize the dataset service.

        Args:
            fdp_client: FDP client for fetching metadata.
        """
        self.fdp_client = fdp_client

    def get_all_datasets(self, fdp_uris: List[str]) -> List[Dataset]:
        """
        Fetch all datasets from the given FDPs.

        Fetches FDPs concurrently, then fetches all discovered catalogs
        concurrently to minimise total wait time.

        Args:
            fdp_uris: List of FDP URIs to fetch from.

        Returns:
            List of all datasets from all FDPs.
        """
        # Step 1: fetch all FDPs concurrently to discover catalogs
        catalog_tasks = []  # list of (catalog_uri, fdp_uri, fdp_title)

        def _fetch_fdp(uri):
            try:
                return self.fdp_client.fetch_fdp(uri)
            except FDPError as e:
                logger.warning(f"Failed to fetch FDP {uri}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_fetch_fdp, uri): uri for uri in fdp_uris}
            for future in as_completed(futures):
                fdp = future.result()
                if fdp:
                    logger.info(f"Fetching datasets from {len(fdp.catalogs)} catalogs in {fdp.title}")
                    for catalog_uri in fdp.catalogs:
                        catalog_tasks.append((catalog_uri, fdp.uri, fdp.title))

        # Step 2: fetch all catalogs concurrently
        datasets = []

        def _fetch_catalog(task):
            catalog_uri, fdp_uri, fdp_title = task
            try:
                return self.fdp_client.fetch_catalog_with_datasets(
                    catalog_uri, fdp_uri, fdp_title
                )
            except FDPError as e:
                logger.warning(f"Failed to fetch catalog {catalog_uri}: {e}")
                return []

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_fetch_catalog, t): t for t in catalog_tasks}
            for future in as_completed(futures):
                datasets.extend(future.result())

        logger.info(f"Total datasets fetched: {len(datasets)}")
        return datasets

    def filter_by_theme(
        self, datasets: List[Dataset], theme_uri: str
    ) -> List[Dataset]:
        """
        Filter datasets by theme URI.

        Args:
            datasets: Datasets to filter.
            theme_uri: Theme URI to filter by.

        Returns:
            Datasets that have the specified theme.
        """
        return [ds for ds in datasets if theme_uri in ds.themes]

    def filter_by_application(
        self, datasets: List[Dataset], key: str
    ) -> List[Dataset]:
        """Filter datasets whose catalog shares the given application key."""
        return [ds for ds in datasets if application_key(ds) == key]

    def get_available_applications(
        self, datasets: List[Dataset]
    ) -> List['Application']:
        """Collate datasets into application groups using application_key().

        The label is the most common ``catalog_title`` seen for that key.
        Catalogs without a published homepage but with the same title across
        FDPs collapse into one application — the typical case for the current
        FDP fleet, where SafeVoice is published from both EEPA and Tangaza.
        """
        from collections import Counter, defaultdict

        titles_per_key: Dict[str, Counter] = defaultdict(Counter)
        fdps_per_key: Dict[str, set] = defaultdict(set)
        datasets_per_key: Dict[str, int] = defaultdict(int)
        homepages_per_key: Dict[str, str] = {}

        for ds in datasets:
            key = application_key(ds)
            if not key:
                continue
            if ds.catalog_title:
                titles_per_key[key][ds.catalog_title] += 1
            if ds.fdp_uri:
                fdps_per_key[key].add(ds.fdp_uri)
            datasets_per_key[key] += 1
            if ds.catalog_homepage and key not in homepages_per_key:
                homepages_per_key[key] = ds.catalog_homepage

        apps = []
        for key, ds_count in datasets_per_key.items():
            if titles_per_key[key]:
                label = titles_per_key[key].most_common(1)[0][0]
            else:
                label = key.split(':', 1)[-1]
            apps.append(Application(
                key=key,
                homepage=homepages_per_key.get(key, ''),
                label=label,
                fdp_count=len(fdps_per_key[key]),
                dataset_count=ds_count,
            ))
        # Most-widely-hosted applications first, then alphabetical.
        apps.sort(key=lambda a: (-a.fdp_count, a.label.lower()))
        return apps

    def search(self, datasets: List[Dataset], query: str) -> List[Dataset]:
        """
        Full-text search across dataset metadata.

        Searches across title, description, and keywords.
        Results are ordered by relevance:
        - Title match (highest priority)
        - Description match
        - Keyword match (lowest priority)

        Args:
            datasets: Datasets to search.
            query: Search query string (case-insensitive).

        Returns:
            Matching datasets, ordered by relevance.
        """
        if not query:
            return datasets

        query_lower = query.lower()
        query_terms = query_lower.split()

        scored_results = []

        for ds in datasets:
            score = 0
            title_lower = (ds.title or '').lower()
            desc_lower = (ds.description or '').lower()
            keywords_lower = [kw.lower() for kw in ds.keywords]

            for term in query_terms:
                # Title match (highest weight)
                if term in title_lower:
                    score += 100
                    # Bonus for exact title match
                    if title_lower == term:
                        score += 50

                # Description match
                if term in desc_lower:
                    score += 10

                # Keyword match
                if any(term in kw for kw in keywords_lower):
                    score += 5
                    # Bonus for exact keyword match
                    if term in keywords_lower:
                        score += 10

                # Theme label match
                theme_labels_lower = [tl.lower() for tl in ds.theme_labels]
                if any(term in tl for tl in theme_labels_lower):
                    score += 5

            if score > 0:
                scored_results.append((score, ds))

        # Sort by score (descending), then by title
        scored_results.sort(key=lambda x: (-x[0], x[1].title or ''))

        return [ds for _, ds in scored_results]

    def get_available_themes(self, datasets: List[Dataset]) -> List[Theme]:
        """
        Extract unique themes from datasets for filter UI.

        Args:
            datasets: Datasets to extract themes from.

        Returns:
            List of Theme objects with uri, label, and count.
        """
        theme_counts: Dict[str, Dict[str, Any]] = {}

        for ds in datasets:
            for i, theme_uri in enumerate(ds.themes):
                if theme_uri not in theme_counts:
                    # Try to get a label
                    label = ''
                    if i < len(ds.theme_labels):
                        label = ds.theme_labels[i]
                    if not label:
                        # Use the last segment of the URI as a fallback label, humanized
                        raw = theme_uri.rstrip('/').split('/')[-1].split('#')[-1]
                        label = humanize_label(raw)

                    theme_counts[theme_uri] = {
                        'uri': theme_uri,
                        'label': label,
                        'count': 0,
                    }

                theme_counts[theme_uri]['count'] += 1

        # Convert to Theme objects and sort by count (descending)
        themes = [
            Theme(
                uri=data['uri'],
                label=data['label'],
                count=data['count'],
            )
            for data in theme_counts.values()
        ]

        themes.sort(key=lambda t: (-t.count, t.label))

        return themes

    def get_available_sources(self, datasets: List[Dataset]) -> List[Source]:
        """Aggregate datasets by FDP for the source chip row on the browse page."""
        counts: Dict[str, Dict[str, Any]] = {}
        for ds in datasets:
            if not ds.fdp_uri:
                continue
            entry = counts.setdefault(ds.fdp_uri, {
                'fdp_uri': ds.fdp_uri,
                'fdp_title': ds.fdp_title or ds.fdp_uri,
                'count': 0,
            })
            entry['count'] += 1
        sources = [Source(**c) for c in counts.values()]
        sources.sort(key=lambda s: (s.fdp_title or '').lower())
        return sources
