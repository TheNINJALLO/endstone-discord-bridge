import sys
import types
from pathlib import Path


package_path = Path(__file__).resolve().parents[1] / "src" / "endstone_discord_bridge"
package = types.ModuleType("endstone_discord_bridge")
package.__path__ = [str(package_path)]
sys.modules.setdefault("endstone_discord_bridge", package)
