import json
import os

with open('scratch/filtered_enriched.json', encoding='utf-8') as f:
    raw_docs = json.load(f)

# List of dedicated high-fidelity Markdown files created
rag_files = [
    {
        'id': '25418',
        'archivo_md': 'normativa/01_marco_general_estatutos/ACUERDO_008_2008_CSU_Estatuto_Estudiantil.md',
        'titulo': 'Acuerdo 008 de 2008 CSU - Estatuto Estudiantil (Créditos, Doble Titulación, Equivalencias, Pérdida de Cupo)',
        'categoria': 'Marco General y Estatutos',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=25418',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '25417',
        'archivo_md': 'normativa/01_marco_general_estatutos/ACUERDO_033_2007_CSU_Lineamientos_Curriculares.md',
        'titulo': 'Acuerdo 033 de 2007 CSU - Lineamientos Básicos de Formación (Estructura en 3 Componentes Curriculares)',
        'categoria': 'Marco General y Estatutos',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=25417',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '73205',
        'archivo_md': 'normativa/01_marco_general_estatutos/ACUERDO_155_2014_CSU_Reglamentacion_Doble_Titulacion.md',
        'titulo': 'Acuerdo 155 de 2014 CSU - Reglamento General del Programa de Doble Titulación en la UNAL',
        'categoria': 'Marco General y Estatutos',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=73205',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '106142',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/ACUERDO_011_2023_CF_Ingenieria_Plan_Estudios_Vigente.md',
        'titulo': 'Acuerdo 011 de 2023 CF Ingeniería Bogotá - Plan de Estudios Vigente (165 créditos, Asignaturas y Malla Curricular)',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=106142',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '103388',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/ACUERDO_003A_2022_CA_Estructura_Curricular_Sistemas.md',
        'titulo': 'Acuerdo 003-A de 2022 Consejo Académico - Estructura Curricular General de Ingeniería de Sistemas (165 créditos)',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=103388',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '73193',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/ACUERDO_097_2014_CA_Plan_Estudios_Historico_168_Creditos.md',
        'titulo': 'Acuerdo 097 de 2014 Consejo Académico - Plan de Estudios Histórico (168 créditos) de Ingeniería de Sistemas',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=73193',
        'vigencia': 'DEROGADO'
    },
    {
        'id': '54466',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/ACUERDO_086_2013_CSU_Denominacion_Titulo_Ingenieria_Sistemas.md',
        'titulo': 'Acuerdo 086 de 2013 CSU - Modificación del Título Oficial a "Ingeniero(a) de Sistemas y Computación"',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=54466',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-EST-SIS-BOG-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_ESTUDIANTE_SISTEMAS_BOGOTA_TRABAJO_GRADO_PRACTICAS_CREDITOS.md',
        'titulo': 'Guía Integral del Estudiante: Trabajo de Grado, Pasantías, Libre Elección (33 cr), PAPI, PAPA y Trámites Académicos',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=106142',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-POS-ELEC-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_MATERIAS_POSGRADO_COMO_ELECTIVAS_COTERMINAL.md',
        'titulo': 'Guía de Asignaturas de Posgrado como Electivas de Libre Elección y Articulación Coterminal (Sistemas Bogotá)',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=112713',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '103243',
        'archivo_md': 'normativa/02_ciencias_computacion_bogota/ACUERDO_487_2022_CF_Ciencias_Plan_Estudios_CC_Bogota_Vigente.md',
        'titulo': 'Acuerdo 487 de 2022 CF Ciencias Bogotá - Plan de Estudios Vigente de Ciencias de la Computación (143 créditos)',
        'categoria': 'Ciencias de la Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=103243',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'COMP-BOG-SIS-CC',
        'archivo_md': 'normativa/02_ciencias_computacion_bogota/COMPARATIVA_SISTEMAS_VS_COMPUTACION_BOGOTA_DOBLE_TITULACION.md',
        'titulo': 'Comparativa Curricular y Régimen de Doble Titulación en Bogotá: Sistemas (165 cr) vs Ciencias de la Computación (143 cr)',
        'categoria': 'Ciencias de la Computación (Bogotá) y Doble Titulación',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=106142',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '88990',
        'archivo_md': 'normativa/03_ciencias_computacion_medellin/ACUERDO_240_2017_CA_Apertura_Ciencias_Computacion_Medellin.md',
        'titulo': 'Acuerdo 240 de 2017 Consejo Académico - Apertura de Ciencias de la Computación (Facultad de Ciencias Medellín)',
        'categoria': 'Ciencias de la Computación (Medellín)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=88990',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'EQ-CC-SIS-01',
        'archivo_md': 'normativa/03_ciencias_computacion_medellin/RESOLUCION_Equivalencias_Ciencias_Computacion_Sistemas.md',
        'titulo': 'Matriz Normativa de Equivalencias y Homologación: Ciencias de la Computación vs. Ingeniería de Sistemas',
        'categoria': 'Equivalencias y Homologaciones',
        'url': 'https://legal.unal.edu.co/rlunal/home/tmt.jsp',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '34480',
        'archivo_md': 'normativa/04_ingenieria_sistemas_informatica_medellin/ACUERDO_043_2009_CA_Estructura_Sistemas_Informatica_Medellin.md',
        'titulo': 'Acuerdo 043 de 2009 Consejo Académico - Estructura de Ingeniería de Sistemas e Informática (Minas Medellín)',
        'categoria': 'Ingeniería de Sistemas e Informática (Medellín)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=34480',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-RAG-DT-01',
        'archivo_md': 'normativa/05_doble_titulacion_equivalencias/GUIA_RAG_Doble_Titulacion_Sistemas_Computacion.md',
        'titulo': 'Guía Maestra de Doble Titulación en Ingeniería de Sistemas y Computación (Nacional e Internacional con Francia)',
        'categoria': 'Doble Titulación y Movilidad',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=73205',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-DT-OTRAS-BOG-01',
        'archivo_md': 'normativa/05_doble_titulacion_equivalencias/GUIA_DOBLE_TITULACION_SISTEMAS_CON_OTRAS_CARRERAS_BOGOTA.md',
        'titulo': 'Guía Maestra de Doble Titulación de Sistemas con Otras Carreras en Bogotá (CC, Matemáticas, Estadística, Electrónica, Industrial)',
        'categoria': 'Doble Titulación y Movilidad',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=73205',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-DT-INTERNACIONAL-01',
        'archivo_md': 'normativa/05_doble_titulacion_equivalencias/GUIA_AMPLIADA_DOBLE_TITULACION_INTERNACIONAL_E_INTERSEDES.md',
        'titulo': 'Guía Ampliada de Doble Titulación Internacional (Grandes Écoles Francia, TU9 Alemania), Intersedes y Convenio SÍGUEME',
        'categoria': 'Doble Titulación y Movilidad',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=73205',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-RAG-EQ-01',
        'archivo_md': 'normativa/05_doble_titulacion_equivalencias/GUIA_RAG_Equivalencias_Homologaciones_Sistemas.md',
        'titulo': 'Régimen General de Equivalencias, Homologaciones y Convalidaciones en Ingeniería y Computación',
        'categoria': 'Equivalencias y Homologaciones',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=25418',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '112713',
        'archivo_md': 'normativa/06_posgrados_articulacion/ACUERDO_008_2025_CF_Ingenieria_Posgrados_Sistemas.md',
        'titulo': 'Acuerdo 008 de 2025 CF Ingeniería - Plan de Estudios de la Maestría en Sistemas y Articulación Coterminal',
        'categoria': 'Posgrados y Articulación Coterminal',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=112713',
        'vigencia': 'VIGENTE'
    },
    {
        'id': '94896',
        'archivo_md': 'normativa/06_posgrados_articulacion/ACUERDO_100_113_117_CF_Ingenieria_Doctorado_Maestria_Sistemas.md',
        'titulo': 'Acuerdos 100, 113 y 117 de 2020 CF Ingeniería - Marco Doctoral y de Maestría en Sistemas y Computación',
        'categoria': 'Posgrados y Articulación Coterminal',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=94896',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-OPC-GRA-SIS-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_OPCIONES_DE_GRADO_DETALLADA_SISTEMAS_BOGOTA.md',
        'titulo': 'Guía Detallada de Opciones de Trabajo de Grado y Titulación: Investigación, Coterminal, Pasantías y Emprendimiento',
        'categoria': 'Ingeniería de Sistemas y Computación (Bogotá)',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=106142',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-EMP-PRAC-SIS-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_EMPLEABILIDAD_PRACTICAS_Y_ALIANZAS_EMPRESARIALES.md',
        'titulo': 'Guía Integral de Oportunidades Laborales, Prácticas Empresariales y Alianzas Estratégicas (OERI / DISI)',
        'categoria': 'Empleabilidad y Alianzas Empresariales',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=106142',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-MOV-INT-DRE-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_MOVILIDAD_INTERNACIONAL_E_INTERCAMBIOS_DRE.md',
        'titulo': 'Guía Completa de Movilidad Internacional, Intercambios Académicos y Becas: DRE UNAL (Magalhães, DAAD, Mitacs, Erasmus+)',
        'categoria': 'Movilidad Internacional e Intercambios',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=73205',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-SEM-EXT-SIS-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_SEMILLEROS_INVESTIGACION_Y_VIDA_EXTRACURRICULAR.md',
        'titulo': 'Guía de Semilleros de Investigación (MIDAS, DIS, GICS, MindLab), Programación Competitiva (Turing / ICPC), Capítulos ACM/IEEE y Bienestar',
        'categoria': 'Semilleros, Vida Extracurricular y Bienestar',
        'url': 'https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i=25418',
        'vigencia': 'VIGENTE'
    },
    {
        'id': 'GUIA-HERMES-INV-01',
        'archivo_md': 'normativa/02_ingenieria_sistemas_bogota/GUIA_HERMES_GRUPOS_SEMILLEROS_Y_CONVOCATORIAS.md',
        'titulo': 'Guía Oficial del Sistema HERMES (hermes.unal.edu.co): Grupos de Investigación, Semilleros, Convocatorias DIB y MinCiencias',
        'categoria': 'Investigación y Sistema HERMES',
        'url': 'https://hermes.unal.edu.co/',
        'vigencia': 'VIGENTE'
    }
]

catalog = {
    'metadata': {
        'nombre': 'Corpus RAG Normativa Universidad Nacional de Colombia - Sede Bogotá (Ingeniería de Sistemas y Ciencias de la Computación)',
        'fuente_oficial': 'Sistema de Información Normativa, Jurisprudencial y de Conceptos "Régimen Legal" (legal.unal.edu.co)',
        'sede_prioritaria': 'Sede Bogotá (Facultades de Ingeniería, Ciencias y Ciencias Económicas)',
        'temas_cubiertos': [
            'Ingeniería de Sistemas y Computación - Bogotá (Acuerdo 011 de 2023 CF Ingeniería - 165 créditos)',
            'Ciencias de la Computación - Bogotá (Acuerdo 487 de 2022 CF Ciencias - 143 créditos)',
            'Materias de Posgrado como Electivas de Libre Elección y Articulación Coterminal',
            'Opciones de Trabajo de Grado (Investigación, Posgrados, Pasantías, Emprendimiento)',
            'Pasantías y Prácticas Empresariales como Libre Elección',
            'Componente de Libre Elección (33 créditos)',
            'PAPI, PAPA, PA y Cupo de Créditos (Bolsa de créditos)',
            'Doble Titulación Internacional (Grandes Écoles Francia: IMT Atlantique, CentraleSupélec, INSA, Telecom Paris)',
            'Doble Titulación Intersedes (Medellín - Manizales) y Convenio SÍGUEME (Los Andes, Javeriana, UdeA, UIS)',
            'Doble Titulación con CC, Matemáticas, Estadística, Electrónica, Industrial y Administración',
            'Protección jurídica del primer título, renuncia voluntaria y grados escalonados',
            'Oportunidades laborales, perfiles profesionales y empleabilidad OLE',
            'Prácticas empresariales, alianzas estratégicas OERI y convenios Big Tech / Fintech',
            'Movilidad Internacional DRE: Red Magalhães, DAAD Alemania, Mitacs Canadá, Erasmus+',
            'Semilleros de investigación DISI (MIDAS, DIS, GICS, MindLab) y Ciencias de la Computación',
            'Programación Competitiva: Club de Algoritmia UNAL y Semillero Turing (Maratones ICPC)',
            'Capítulos Estudiantiles (ACM, IEEE Computer Society, IEEE WIE) y Bienestar Universitario (Deportes, Cultura, Apoyos)',
            'Sistema de Información de la Investigación HERMES (hermes.unal.edu.co), Convocatorias DIB, MinCiencias (GrupLAC/CvLAC) y Certificados Oficiales'
        ],
        'total_documentos_detallados_rag': len(rag_files),
        'total_registros_normativos_extraidos': len(raw_docs)
    },
    'documentos_rag_principales': rag_files,
    'inventario_completo_legal_unal': []
}

for doc_id, d in raw_docs.items():
    catalog['inventario_completo_legal_unal'].append({
        'id_legal_unal': doc_id,
        'tipo': d.get('tipo', ''),
        'numero': d.get('numero', ''),
        'ano': d.get('ano', ''),
        'autoridad_emisora': d.get('emisor', ''),
        'url_oficial': d.get('url', f"https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i={doc_id}"),
        'tema': d.get('tema', ''),
        'subtema': d.get('subtema', ''),
        'epigrafe_oficial': d.get('epigrafe', ''),
        'derogaciones_registradas': d.get('derogaciones', []),
        'consultas_asociadas': d.get('queries', [])
    })

with open('CATALOGO_NORMATIVO_RAG.json', 'w', encoding='utf-8') as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

print(f"Catálogo RAG actualizado exitosamente:")
print(f"  - Documentos RAG de alta fidelidad: {len(rag_files)}")
print(f"  - Registros de legal.unal.edu.co indexados: {len(catalog['inventario_completo_legal_unal'])}")
