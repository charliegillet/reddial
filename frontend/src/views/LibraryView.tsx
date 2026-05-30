import { Library as LibraryIcon } from "lucide-react";
import { motion } from "framer-motion";
import { type Attack } from "../api";

interface LibraryViewProps {
  attacks: Attack[];
}

export function LibraryView({ attacks }: LibraryViewProps) {
  return (
    <motion.div
      initial={{ y: 10 }}
      animate={{ y: 0 }}
    >
      <div className="card">
        <div className="card-header">
          <LibraryIcon size={18} className="brand-icon" />
          <span className="card-title">Attack Library ({attacks.length})</span>
        </div>
        {attacks.length === 0 ? (
          <div className="card-body">
            <div className="view-empty">
              <LibraryIcon size={28} />
              <p>No attacks loaded.</p>
            </div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Category</th>
                <th style={{ width: "42%" }}>Spoken Template</th>
                <th>Success Condition</th>
              </tr>
            </thead>
            <tbody>
              {attacks.map((a, i) => (
                <motion.tr
                  key={a.id}
                  initial={{ x: -8 }}
                  animate={{ x: 0 }}
                  transition={{ duration: 0.3, delay: 0.04 * i }}
                >
                  <td className="cell-id">{a.id}</td>
                  <td>
                    <span className="attack-category">{a.category}</span>
                  </td>
                  <td className="cell-template">"{a.spoken_template}"</td>
                  <td className="cell-numeric">{a.success_condition}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </motion.div>
  );
}
