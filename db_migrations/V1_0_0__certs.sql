CREATE SCHEMA IF NOT EXISTS certs;

CREATE TABLE IF NOT EXISTS certs.root_ca (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    master_list_issuer        TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS certs.dsc (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS certs.crls (
    id          UUID PRIMARY KEY,
    crl         BYTEA NOT NULL,
    source      TEXT,
    issuer      TEXT,
    country     TEXT,
    updated_at  TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS certs.revoked_certificate_list (
    id                UUID PRIMARY KEY,
    source            TEXT,
    country           TEXT,
    isn               TEXT,
    crl               UUID REFERENCES certs.crls(id),
    revocation_reason TEXT,
    revocation_date   TIMESTAMP WITHOUT TIME ZONE,
    updated_at        TIMESTAMP WITHOUT TIME ZONE
);