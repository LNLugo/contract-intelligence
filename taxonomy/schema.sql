-- Governed clause taxonomy (ADR-0011). Legal owns the content; versions move draft -> approved -> retired.
-- Only the approved version is used at runtime; a draft can be edited and evaluated before approval.

CREATE TABLE IF NOT EXISTS taxonomy_version (
    version      text PRIMARY KEY,
    status       text NOT NULL CHECK (status IN ('draft', 'approved', 'retired')),
    source       text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    approved_by  text,
    approved_at  timestamptz
);

-- At most one approved version at a time
CREATE UNIQUE INDEX IF NOT EXISTS one_approved_version
    ON taxonomy_version (status) WHERE status = 'approved';

CREATE TABLE IF NOT EXISTS clause_category (
    version     text NOT NULL REFERENCES taxonomy_version (version),
    code        text NOT NULL,                 -- stable key, e.g. cap_on_liability
    name        text NOT NULL,                 -- CUAD label, e.g. Cap On Liability
    definition  text NOT NULL,                 -- what the category means
    includes    text[] NOT NULL DEFAULT '{}',  -- forms that DO count (filled by Legal)
    excludes    text[] NOT NULL DEFAULT '{}',  -- related forms that do NOT count
    owner       text NOT NULL DEFAULT 'Legal',
    PRIMARY KEY (version, code)
);

-- Terms that map to a category, for query normalization ("cap on damages" -> cap_on_liability)
CREATE TABLE IF NOT EXISTS category_term (
    version  text NOT NULL,
    code     text NOT NULL,
    term     text NOT NULL,
    PRIMARY KEY (version, code, term),
    FOREIGN KEY (version, code) REFERENCES clause_category (version, code)
);

-- Terms the system could not map: logged for Legal review, never forced into a category
CREATE TABLE IF NOT EXISTS unmapped_term (
    id         bigserial PRIMARY KEY,
    term       text NOT NULL,
    seen_in    text,
    seen_at    timestamptz NOT NULL DEFAULT now(),
    resolved   boolean NOT NULL DEFAULT false
);
