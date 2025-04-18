import ast
import streamlit as st
#ChatGPT was used to help create this more bare bones implemenation of this compiler

class MiniCompiler(ast.NodeVisitor):
    def __init__(self):
        self.param = None
        self.loop_var = None
        self.inits = {}  # accumulator initial values
        self.cond = None
        self.updates = {}  # accumulator update expressions
        self.cte_rows = []

    def compile(self, source: str) -> str:
        # Reset state
        self.param = None
        self.loop_var = None
        self.inits.clear()
        self.cond = None
        self.updates.clear()
        self.cte_rows = []
        tree = ast.parse(source)
        # Process function
        self.visit(tree)
        return self._emit_cte()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Single list parameter
        self.param = node.args.args[0].arg
        # Scan initial assignments until For
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                self.inits[name] = ast.unparse(stmt.value)
            elif isinstance(stmt, ast.For):
                # Found loop: record loop variable and process
                self.loop_var = stmt.target.id
                self._process_loop(stmt)
                break
        # Anchor member: idx, loop_var, and initial accumulators
        cols = ["1 AS idx", f"{self.param}[1] AS {self.loop_var}"]
        for name, value in self.inits.items():
            cols.append(f"{value} AS {name}")
        self.cte_rows.append("SELECT " + ", ".join(cols))

    def _process_loop(self, node: ast.For):
        # Extract If in loop body if present
        for stmt in node.body:
            if isinstance(stmt, ast.If):
                self.cond = ast.unparse(stmt.test)
                # Look for AugAssign inside If
                for sub in stmt.body:
                    if isinstance(sub, ast.AugAssign) and isinstance(sub.target, ast.Name):
                        name = sub.target.id
                        expr = ast.unparse(sub.value)
                        self.updates[name] = expr
        # Build recursive member
        cols = ["idx + 1 AS idx", f"{self.param}[idx+1] AS {self.loop_var}"]
        for name in self.inits:
            if name in self.updates and self.cond:
                # conditional update
                expr = self.updates[name]
                cols.append(
                    f"CASE WHEN {self.cond} THEN {name} + ({expr}) ELSE {name} END AS {name}"
                )
            else:
                # carry over
                cols.append(f"{name} AS {name}")
        recursive = "UNION ALL SELECT " + ", ".join(cols) + f" FROM cte WHERE idx < array_length({self.param}, 1)"
        self.cte_rows.append(recursive)

    def _emit_cte(self) -> str:
        body = "\n    ".join(self.cte_rows)
        sql = (
            "WITH RECURSIVE cte AS (\n"
            f"    {body}\n"
            ")\n"
            f"SELECT *\nFROM cte WHERE idx = array_length({self.param}, 1);"
        )
        return sql

# Initialize session state variables
if 'code_input' not in st.session_state:
    st.session_state.code_input = ""

if 'previous_code_input' not in st.session_state:
    st.session_state.previous_code_input = st.session_state.code_input

if 'sql_output' not in st.session_state:
    st.session_state.sql_output = ""

# Define the clear function
def clear_inputs():
    # Save current code input before clearing
    st.session_state.previous_code_input = st.session_state.code_input
    st.session_state.code_input = ""
    st.session_state.sql_output = ""

# Define the undo function
def undo_clear():
    # Restore code input from previous_code_input
    st.session_state.code_input = st.session_state.previous_code_input

# Streamlit UI
st.title("ByePy Compiler Interface")
st.sidebar.header("Paste Python Function Here:")

# Text area for code input
st.sidebar.text_area("Function Source", key="code_input")

# Buttons
if st.sidebar.button("Compile to SQL"):
    try:
        compiler = MiniCompiler()
        st.session_state.sql_output = compiler.compile(st.session_state.code_input)
    except Exception as e:
        st.session_state.sql_output = f"Compilation error: {e}"

st.sidebar.button("Clear", on_click=clear_inputs)
st.sidebar.button("Undo", on_click=undo_clear)

# Display the SQL output
st.subheader("Generated SQL")
st.markdown(f"```sql\n{st.session_state.sql_output}\n```", unsafe_allow_html=True)
