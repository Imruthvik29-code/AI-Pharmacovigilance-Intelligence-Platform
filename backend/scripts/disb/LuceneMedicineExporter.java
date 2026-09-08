import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexableField;
import org.apache.lucene.index.IndexReader;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;

/**
 * Streams the DISB medicine Lucene index to a TSV file.
 *
 * DISB v1.25 ships the medicine catalog as a Lucene index rather than a
 * relational export. This tiny dependency-free helper (apart from the
 * Lucene core jar already shipped inside DISB) keeps the Python importer
 * focused on validation and PostgreSQL persistence.
 *
 * Usage:
 *   java -cp lucene-core.jar:exporter-classes LuceneMedicineExporter <medicine-index> <output-tsv>
 *
 * The output intentionally contains only the medicine fields needed by the
 * application catalog. The DISB package itself must never be committed to
 * the repository.
 */
public final class LuceneMedicineExporter {
    private static final String[] FIELDS = {
        "id",
        "medicineName",
        "medicineSctid",
        "brand.brandSctid",
        "brand.brandName",
        "manufacturer.manufacturerName",
        "manufacturer.sctid",
        "manufacturer.country",
        "generic.sctid",
        "generic.genericName",
        "licenseNumber",
        "licenseStatus",
        "lastUpdatedon"
    };

    private LuceneMedicineExporter() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: LuceneMedicineExporter <medicine-index> <output-tsv>");
            System.exit(2);
        }

        Path index = Paths.get(args[0]);
        Path output = Paths.get(args[1]);
        Files.createDirectories(output.toAbsolutePath().getParent());

        try (Directory directory = FSDirectory.open(index);
             IndexReader reader = DirectoryReader.open(directory);
             BufferedWriter writer = Files.newBufferedWriter(
                 output, StandardCharsets.UTF_8)) {
            writer.write("id\tmedicineName\tmedicineSctid\tbrandSctid\tbrandName\t"
                + "manufacturerName\tmanufacturerSctid\tmanufacturerCountry\t"
                + "genericSctid\tgenericName\tlicenseNumber\tlicenseStatus\tlastUpdatedon\n");

            var storedFields = reader.storedFields();
            for (int docId = 0; docId < reader.maxDoc(); docId++) {
                if (reader.hasDeletions() && reader.leaves().stream().noneMatch(
                        leaf -> docId >= leaf.docBase && docId < leaf.docBase + leaf.reader().maxDoc())) {
                    continue;
                }
                Document document = storedFields.document(docId);
                if (document.get("id") == null || document.get("medicineName") == null) {
                    continue;
                }
                for (int i = 0; i < FIELDS.length; i++) {
                    if (i > 0) writer.write('\t');
                    writer.write(escape(document.get(FIELDS[i])));
                }
                writer.write('\n');
            }
        }
    }

    private static String escape(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\")
                    .replace("\t", " ")
                    .replace("\r", " ")
                    .replace("\n", " ");
    }
}
