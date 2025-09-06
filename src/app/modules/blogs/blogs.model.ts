import { Schema, model, Document, Types } from "mongoose";
import { IBlog } from "./blog.interface";



const BlogSchema = new Schema<IBlog>(
  {
    title: {
      type: String,
      required: true,
      trim: true,
    },
    image: {
      type: String,
      required: true,
    },
    description: {
      type: String,
      required: true,
    },
  },
  {
    timestamps: true,
  }
);

const Blog = model<IBlog>("Blog", BlogSchema);

export default Blog;
