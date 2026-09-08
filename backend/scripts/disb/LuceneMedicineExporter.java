import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexReader;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;

/**
 * Streams the DISB medicine Lucene index to a TSV file.
 *
 * DISB v1.25 ships the medicine catalog as a Lucene index rather than a
 * relational export. This tiny helper uses only the Lucene core jar already
 * shipped inside DISB, keeping the Python importer focused on validation and
 * PostgreSQL persistence.
 *
 * The DISB package itself must never be committed to the repository.
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
        Path parent = output.toAbsolutePath().getParent();
        if (parent != null) Files.createDirectories(parent);

        try (Directory directory = FSDirectory.open(index);
             IndexReader reader = DirectoryReader.open(directory)) {
            var storedFields = reader.storedFields();
            try (var writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
                writer.write("id\tmedicineName\tmedicineSctid\tbrandSctid\tbrandName\t"
                    + "manufacturerName\tmanufacturerSctid\tmanufacturerCountry\t"
                    + "genericSctid\tgenericName\tlicenseNumber\tlicenseStatus\tlastUpdatedon\n");

                for (var leaf : reader.leaves()) {
                    var liveDocs = leaf.reader().getLiveDocs();
                    for (int localDocId = 0; localDocId < leaf.reader().maxDoc(); localDocId++) {
                        if (liveDocs != null && !liveDocs.get(localDocId)) continue;
                        int docId = leaf.docBase + localDocId;
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
