import json

with open('scratch/found_docs.json', encoding='utf-8') as f:
    docs = json.load(f)

print(f"Total documents: {len(docs)}")

# Summary by authority (emisor)
emisores = {}
tipos = {}
anos = {}

for doc_id, doc in docs.items():
    em = doc.get('emisor', 'Desconocido')
    tp = doc.get('tipo', 'Desconocido')
    an = doc.get('ano', 'Desconocido')
    emisores[em] = emisores.get(em, 0) + 1
    tipos[tp] = tipos.get(tp, 0) + 1
    anos[an] = anos.get(an, 0) + 1

print("\n--- Por Tipo de Documento ---")
for tp, cnt in sorted(tipos.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {tp}: {cnt}")

print("\n--- Por Autoridad (Top 10) ---")
for em, cnt in sorted(emisores.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {em}: {cnt}")

print("\n--- Por Año (Recientes) ---")
for an, cnt in sorted(anos.items(), key=lambda x: str(x[0]), reverse=True)[:10]:
    print(f"  {an}: {cnt}")
