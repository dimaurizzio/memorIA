-- Habilitar extensión de vectores (necesaria para RAG)
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabla principal de documentos generados por los agentes
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  object_type TEXT NOT NULL CHECK (object_type IN ('table', 'view', 'dashboard', 'stored_procedure')),
  business_domain TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'delisted')),
  owner TEXT NOT NULL,
  content JSONB NOT NULL,         -- contenido completo según schema base
  last_audit_issues JSONB DEFAULT NULL,  -- issues del último audit (null = sin observaciones)
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  approved_at TIMESTAMPTZ,
  approved_by TEXT,
  is_manual_override BOOLEAN DEFAULT FALSE
);

-- Embeddings de documentos aprobados para búsqueda semántica (RAG)
CREATE TABLE document_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  embedding vector(768),          -- dimensión de text-embedding-004
  content_text TEXT NOT NULL,     -- texto plano del doc para contexto
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índice de búsqueda semántica sobre los embeddings
CREATE INDEX ON document_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Registro de cambios de estado de documentos (quién aprobó/rechazó y cuándo)
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id),
  user_id TEXT NOT NULL,
  previous_status TEXT,
  new_status TEXT NOT NULL,
  approval_type TEXT CHECK (approval_type IN ('automatic', 'manual_override')),
  notes TEXT,                     -- observaciones del auditor o razón del override
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Registro de todas las acciones de usuarios en el sistema
CREATE TABLE action_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,           -- 'generate', 'submit_audit', 'approve', 'reject', 'override'
  document_id UUID REFERENCES documents(id),
  metadata JSONB,                 -- info adicional según la acción
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de conversaciones con los agentes (generator, auditor, consultant)
CREATE TABLE conversation_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  agent_type TEXT NOT NULL CHECK (agent_type IN ('generator', 'auditor', 'consultant')),
  document_id UUID REFERENCES documents(id),
  prompt TEXT NOT NULL,
  response TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Usuarios del sistema con sus roles
CREATE TABLE users (
  id TEXT PRIMARY KEY,            -- username o email
  role TEXT NOT NULL DEFAULT 'developer' CHECK (role IN ('developer', 'admin')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Función para búsqueda semántica en documentos aprobados
CREATE OR REPLACE FUNCTION search_documents(
  query_embedding vector(768),
  match_count INT DEFAULT 5,
  similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
  document_id UUID,
  content_text TEXT,
  similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    de.document_id,
    de.content_text,
    1 - (de.embedding <=> query_embedding) AS similarity
  FROM document_embeddings de
  JOIN documents d ON d.id = de.document_id
  WHERE d.status = 'approved'
    AND 1 - (de.embedding <=> query_embedding) > similarity_threshold
  ORDER BY de.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Trigger para mantener updated_at actualizado automáticamente
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_updated_at
  BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
