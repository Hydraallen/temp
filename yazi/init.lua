require("git"):setup()
require("starship"):setup()
require("yaziline"):setup()
require("eza-preview"):setup()

require("yamb"):setup {
	bookmarks = {
		{ tag = "Desktop", path = "~/Desktop/", key = "d" },
		{ tag = "Study", path = "~/Desktop/Study/", key = "s" },
	},
}
