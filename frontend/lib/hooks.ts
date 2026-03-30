import useSWR from "swr";
import { getObjectTypes, getDocSpec } from "@/lib/api";
import type { ObjectTypeInfo, DocSpec } from "@/lib/types";

const FALLBACK: ObjectTypeInfo[] = [
  { value: "table",            label: "TABLA",       display_name: "Tabla",             icon: "🗄️" },
  { value: "view",             label: "VISTA",       display_name: "Vista",             icon: "🔍" },
  { value: "dashboard",        label: "DASHBOARD",   display_name: "Dashboard",         icon: "📊" },
  { value: "stored_procedure", label: "STORED PROC", display_name: "Stored Procedure",  icon: "⚙️" },
];

/**
 * Retorna el spec completo (secciones + campos) para un tipo de objeto.
 * Cacheado 30 min — si el spec cambia, basta con hacer un hard refresh.
 */
export function useDocSpec(objectType: string): DocSpec | null {
  const { data } = useSWR<DocSpec>(
    `spec:${objectType}`,
    () => getDocSpec(objectType),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 60_000 * 30,
    }
  );
  return data ?? null;
}

/**
 * Retorna los tipos de objeto soportados desde la API.
 * Mientras carga o si falla, devuelve el fallback estático para no bloquear la UI.
 */
export function useObjectTypes() {
  const { data } = useSWR<ObjectTypeInfo[]>("spec:types", getObjectTypes, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 60_000 * 10, // re-fetch máximo cada 10 min
  });
  return data ?? FALLBACK;
}
