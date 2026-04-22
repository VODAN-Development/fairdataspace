"""Data models for Datasets, Distributions, and Contact Points."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ContactPoint:
    """Contact information for data requests."""

    name: Optional[str] = None
    email: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'email': self.email,
            'url': self.url,
        }


@dataclass
class Distribution:
    """Represents a DCAT Distribution with access and endpoint metadata."""

    uri: str
    title: Optional[str] = None
    description: Optional[str] = None
    access_url: Optional[str] = None
    download_url: Optional[str] = None
    media_type: Optional[str] = None
    format: Optional[str] = None
    byte_size: Optional[int] = None
    # SPARQL / DataService endpoint info
    endpoint_url: Optional[str] = None
    endpoint_description: Optional[str] = None
    is_sparql_endpoint: bool = False
    # Contact at distribution level
    contact_point: Optional[ContactPoint] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'uri': self.uri,
            'title': self.title,
            'description': self.description,
            'access_url': self.access_url,
            'download_url': self.download_url,
            'media_type': self.media_type,
            'format': self.format,
            'byte_size': self.byte_size,
            'endpoint_url': self.endpoint_url,
            'endpoint_description': self.endpoint_description,
            'is_sparql_endpoint': self.is_sparql_endpoint,
            'contact_point': self.contact_point.to_dict() if self.contact_point else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Distribution':
        """Create a Distribution from a dictionary."""
        contact_data = data.get('contact_point')
        contact_point = None
        if contact_data:
            contact_point = ContactPoint(
                name=contact_data.get('name'),
                email=contact_data.get('email'),
                url=contact_data.get('url'),
            )
        return cls(
            uri=data['uri'],
            title=data.get('title'),
            description=data.get('description'),
            access_url=data.get('access_url'),
            download_url=data.get('download_url'),
            media_type=data.get('media_type'),
            format=data.get('format'),
            byte_size=data.get('byte_size'),
            endpoint_url=data.get('endpoint_url'),
            endpoint_description=data.get('endpoint_description'),
            is_sparql_endpoint=data.get('is_sparql_endpoint', False),
            contact_point=contact_point,
        )


@dataclass
class Dataset:
    """Represents a DCAT Dataset with all relevant metadata for discovery."""

    uri: str
    title: str
    catalog_uri: str
    fdp_uri: str
    fdp_title: str
    catalog_title: Optional[str] = None
    # Catalog-level application homepage — shared across FDPs that host the same application.
    catalog_homepage: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    creator: Optional[str] = None
    issued: Optional[datetime] = None
    modified: Optional[datetime] = None
    themes: List[str] = field(default_factory=list)
    theme_labels: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    contact_point: Optional[ContactPoint] = None
    landing_page: Optional[str] = None
    distributions: List[Distribution] = field(default_factory=list)

    @property
    def sparql_endpoints(self) -> List[Distribution]:
        """Get distributions that are SPARQL endpoints."""
        return [d for d in self.distributions if d.is_sparql_endpoint]

    @property
    def all_contact_emails(self) -> List[str]:
        """Collect all contact emails from dataset and distribution levels."""
        emails = []
        if self.contact_point and self.contact_point.email:
            emails.append(self.contact_point.email)
        for dist in self.distributions:
            if dist.contact_point and dist.contact_point.email:
                if dist.contact_point.email not in emails:
                    emails.append(dist.contact_point.email)
        return emails

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'uri': self.uri,
            'title': self.title,
            'description': self.description,
            'publisher': self.publisher,
            'creator': self.creator,
            'issued': self.issued.isoformat() if self.issued else None,
            'modified': self.modified.isoformat() if self.modified else None,
            'themes': self.themes,
            'theme_labels': self.theme_labels,
            'keywords': self.keywords,
            'contact_point': self.contact_point.to_dict() if self.contact_point else None,
            'landing_page': self.landing_page,
            'catalog_uri': self.catalog_uri,
            'catalog_title': self.catalog_title,
            'catalog_homepage': self.catalog_homepage,
            'fdp_uri': self.fdp_uri,
            'fdp_title': self.fdp_title,
            'distributions': [d.to_dict() for d in self.distributions],
        }

    def to_minimal_dict(self) -> Dict[str, Any]:
        """Convert to minimal dictionary for session caching (to reduce size)."""
        return {
            'uri': self.uri,
            'title': self.title,
            'catalog_uri': self.catalog_uri,
            'catalog_title': self.catalog_title,
            'catalog_homepage': self.catalog_homepage,
            'fdp_uri': self.fdp_uri,
            'fdp_title': self.fdp_title,
            'description': self.description,
            'themes': self.themes,
            'keywords': self.keywords,
            'contact_point': self.contact_point.to_dict() if self.contact_point else None,
            'landing_page': self.landing_page,
            'distribution_count': len(self.distributions),
        }
